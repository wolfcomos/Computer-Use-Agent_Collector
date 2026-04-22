/**
 * @file win32_capture.cpp
 * @brief Native Windows screen capture using Win32 GDI.
 */

#include "pipewire_capture.h"

#ifdef _WIN32

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <iostream>
#include <thread>

namespace cua {

namespace {

double steady_now_sec() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

}  // namespace

PipeWireCapture::PipeWireCapture(RingBuffer& buffer, int target_fps)
    : buffer_(buffer)
    , target_fps_(std::max(1, target_fps))
    , min_frame_interval_(1.0 / static_cast<double>(std::max(1, target_fps))) {
}

PipeWireCapture::~PipeWireCapture() {
    stop();
}

void PipeWireCapture::log_status(const std::string& msg) {
    if (status_cb_) {
        status_cb_(msg);
    } else {
        std::cerr << "[Win32Capture] " << msg << std::endl;
    }
}

bool PipeWireCapture::init_portal(const std::string&) {
    SetProcessDPIAware();

    virtual_left_ = GetSystemMetrics(SM_XVIRTUALSCREEN);
    virtual_top_ = GetSystemMetrics(SM_YVIRTUALSCREEN);
    const int virtual_width = GetSystemMetrics(SM_CXVIRTUALSCREEN);
    const int virtual_height = GetSystemMetrics(SM_CYVIRTUALSCREEN);

    capture_width_ = std::min(virtual_width, buffer_.max_width());
    capture_height_ = std::min(virtual_height, buffer_.max_height());

    if (capture_width_ <= 0 || capture_height_ <= 0) {
        log_status("Unable to detect a usable virtual desktop size");
        initialized_ = false;
        return false;
    }

    if (capture_width_ != virtual_width || capture_height_ != virtual_height) {
        log_status(
            "Virtual desktop exceeds max frame size; capturing " +
            std::to_string(capture_width_) + "x" +
            std::to_string(capture_height_) + " from the virtual origin"
        );
    } else {
        log_status(
            "Virtual desktop ready: " + std::to_string(capture_width_) + "x" +
            std::to_string(capture_height_)
        );
    }

    initialized_ = true;
    return true;
}

void PipeWireCapture::start() {
    if (running_.load()) return;
    if (!initialized_) {
        log_status("Capture not initialized; skipping live capture start");
        return;
    }

    running_.store(true);
    capture_thread_ = std::thread([this]() {
        capture_loop();
    });
}

void PipeWireCapture::stop() {
    if (!running_.exchange(false)) return;

    if (capture_thread_.joinable()) {
        capture_thread_.join();
    }
}

void PipeWireCapture::capture_loop() {
    while (running_.load()) {
        const double start = steady_now_sec();
        if (!capture_frame()) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            continue;
        }

        const double elapsed = steady_now_sec() - start;
        const double remaining = min_frame_interval_ - elapsed;
        if (remaining > 0.0) {
            std::this_thread::sleep_for(std::chrono::duration<double>(remaining));
        }
    }
}

bool PipeWireCapture::capture_frame() {
    HDC screen_dc = GetDC(nullptr);
    if (!screen_dc) {
        log_status("GetDC(nullptr) failed: " + std::to_string(GetLastError()));
        return false;
    }

    HDC memory_dc = CreateCompatibleDC(screen_dc);
    if (!memory_dc) {
        log_status("CreateCompatibleDC failed: " + std::to_string(GetLastError()));
        ReleaseDC(nullptr, screen_dc);
        return false;
    }

    BITMAPINFO bmi {};
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmi.bmiHeader.biWidth = capture_width_;
    bmi.bmiHeader.biHeight = -capture_height_;  // top-down rows
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;

    void* pixels = nullptr;
    HBITMAP bitmap = CreateDIBSection(
        screen_dc, &bmi, DIB_RGB_COLORS, &pixels, nullptr, 0
    );
    if (!bitmap || !pixels) {
        log_status("CreateDIBSection failed: " + std::to_string(GetLastError()));
        DeleteDC(memory_dc);
        ReleaseDC(nullptr, screen_dc);
        return false;
    }

    HGDIOBJ old = SelectObject(memory_dc, bitmap);
    const BOOL ok = BitBlt(
        memory_dc,
        0,
        0,
        capture_width_,
        capture_height_,
        screen_dc,
        virtual_left_,
        virtual_top_,
        SRCCOPY | CAPTUREBLT
    );

    if (!ok) {
        log_status("BitBlt failed: " + std::to_string(GetLastError()));
        SelectObject(memory_dc, old);
        DeleteObject(bitmap);
        DeleteDC(memory_dc);
        ReleaseDC(nullptr, screen_dc);
        return false;
    }

    const double now = steady_now_sec();
    if (last_frame_ts_ > 0.0 && (now - last_frame_ts_) < min_frame_interval_) {
        SelectObject(memory_dc, old);
        DeleteObject(bitmap);
        DeleteDC(memory_dc);
        ReleaseDC(nullptr, screen_dc);
        return true;
    }

    FrameSlot& slot = buffer_.begin_write();
    slot.timestamp_sec = now;
    slot.width = capture_width_;
    slot.height = capture_height_;

    const auto* src = static_cast<const unsigned char*>(pixels);
    auto* dst = slot.rgb_data.data();
    const size_t pixel_count = static_cast<size_t>(capture_width_) * capture_height_;

    for (size_t i = 0; i < pixel_count; ++i) {
        const size_t si = i * 4;
        const size_t di = i * 3;
        dst[di + 0] = src[si + 2];
        dst[di + 1] = src[si + 1];
        dst[di + 2] = src[si + 0];
    }

    buffer_.commit_write();
    last_frame_ts_ = now;

    SelectObject(memory_dc, old);
    DeleteObject(bitmap);
    DeleteDC(memory_dc);
    ReleaseDC(nullptr, screen_dc);
    return true;
}

}  // namespace cua

#endif
