#include "flutter_window.h"

#include <flutter/standard_method_codec.h>
#include <shellapi.h>

#include <optional>
#include <string>

#include "flutter/generated_plugin_registrant.h"
#include "resource.h"

namespace {

constexpr UINT kNotificationIconId = 1001;
constexpr UINT kNotificationCallbackMessage = WM_APP + 1;

std::wstring Utf16FromUtf8(const std::string& value) {
  if (value.empty()) {
    return std::wstring();
  }
  int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                                   static_cast<int>(value.size()), nullptr, 0);
  if (length <= 0) {
    return std::wstring();
  }
  std::wstring converted(length, L'\0');
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                      static_cast<int>(value.size()), converted.data(), length);
  return converted;
}

std::string StringArgument(const flutter::EncodableMap& arguments,
                           const char* key) {
  const auto iterator = arguments.find(flutter::EncodableValue(key));
  if (iterator == arguments.end()) {
    return std::string();
  }
  const auto* value = std::get_if<std::string>(&iterator->second);
  return value == nullptr ? std::string() : *value;
}

}  // namespace

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  RegisterNotificationChannel();
  InitializeNotificationIcon();
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  if (notification_icon_added_) {
    Shell_NotifyIconW(NIM_DELETE, &notification_icon_);
    notification_icon_added_ = false;
  }
  notification_channel_.reset();
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

void FlutterWindow::RegisterNotificationChannel() {
  notification_channel_ =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          flutter_controller_->engine()->messenger(),
          "sagopalgo/windows_notification",
          &flutter::StandardMethodCodec::GetInstance());
  notification_channel_->SetMethodCallHandler(
      [this](const auto& call, auto result) {
        if (call.method_name() != "show") {
          result->NotImplemented();
          return;
        }
        const auto* arguments =
            std::get_if<flutter::EncodableMap>(call.arguments());
        if (arguments == nullptr) {
          result->Error("INVALID_ARGUMENT", "Notification arguments missing");
          return;
        }
        const bool shown =
            ShowNotification(StringArgument(*arguments, "title"),
                             StringArgument(*arguments, "body"));
        if (!shown) {
          result->Error("NOTIFICATION_FAILED",
                        "Windows notification could not be displayed");
          return;
        }
        result->Success();
      });
}

bool FlutterWindow::InitializeNotificationIcon() {
  notification_icon_.cbSize = sizeof(NOTIFYICONDATAW);
  notification_icon_.hWnd = GetHandle();
  notification_icon_.uID = kNotificationIconId;
  notification_icon_.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
  notification_icon_.uCallbackMessage = kNotificationCallbackMessage;
  notification_icon_.hIcon = static_cast<HICON>(LoadImageW(
      GetModuleHandle(nullptr), MAKEINTRESOURCE(IDI_APP_ICON), IMAGE_ICON, 0, 0,
      LR_DEFAULTSIZE | LR_SHARED));
  wcscpy_s(notification_icon_.szTip, L"SagoPalgo notifications");
  notification_icon_added_ =
      Shell_NotifyIconW(NIM_ADD, &notification_icon_) == TRUE;
  if (notification_icon_added_) {
    notification_icon_.uVersion = NOTIFYICON_VERSION_4;
    Shell_NotifyIconW(NIM_SETVERSION, &notification_icon_);
  }
  return notification_icon_added_;
}

bool FlutterWindow::ShowNotification(const std::string& title,
                                     const std::string& body) {
  if (!notification_icon_added_ && !InitializeNotificationIcon()) {
    return false;
  }
  const std::wstring wide_title = Utf16FromUtf8(title);
  const std::wstring wide_body = Utf16FromUtf8(body);
  notification_icon_.uFlags = NIF_INFO;
  notification_icon_.dwInfoFlags = NIIF_INFO | NIIF_LARGE_ICON;
  wcsncpy_s(notification_icon_.szInfoTitle, wide_title.c_str(), _TRUNCATE);
  wcsncpy_s(notification_icon_.szInfo, wide_body.c_str(), _TRUNCATE);
  return Shell_NotifyIconW(NIM_MODIFY, &notification_icon_) == TRUE;
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
