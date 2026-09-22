#include "flutter_window.h"

#include <flutter/standard_method_codec.h>
#include <shellapi.h>
#include <wincred.h>

#include <optional>
#include <string>

#include "flutter/generated_plugin_registrant.h"
#include "resource.h"

namespace {

constexpr UINT kNotificationIconId = 1001;
constexpr UINT kNotificationCallbackMessage = WM_APP + 1;
constexpr UINT kTrayShowDashboard = 1101;
constexpr UINT kTrayMiniMode = 1102;
constexpr UINT kTrayRefresh = 1103;
constexpr UINT kTraySettings = 1104;
constexpr UINT kTrayExit = 1105;

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

std::string Utf8FromUtf16(const std::wstring& value) {
  if (value.empty()) {
    return std::string();
  }
  int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
                                   static_cast<int>(value.size()), nullptr, 0,
                                   nullptr, nullptr);
  if (length <= 0) {
    return std::string();
  }
  std::string converted(length, '\0');
  WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
                      static_cast<int>(value.size()), converted.data(), length,
                      nullptr, nullptr);
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

bool IsSagoPalgoCredentialTarget(const std::wstring& target) {
  return target.rfind(L"SagoPalgo/", 0) == 0;
}

std::string WindowsErrorMessage(const char* operation, DWORD error) {
  return std::string(operation) + " failed with Windows error " +
         std::to_string(error);
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
  RegisterCredentialChannel();
  RegisterWindowControlChannel();
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
  credential_channel_.reset();
  window_control_channel_.reset();
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

void FlutterWindow::RegisterWindowControlChannel() {
  window_control_channel_ =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          flutter_controller_->engine()->messenger(),
          "sagopalgo/window_control",
          &flutter::StandardMethodCodec::GetInstance());
  window_control_channel_->SetMethodCallHandler(
      [this](const auto& call, auto result) {
        if (call.method_name() == "showDashboard") {
          ShowDashboardWindow();
          result->Success();
          return;
        }
        if (call.method_name() == "enterMiniMode") {
          EnterMiniMode();
          result->Success();
          return;
        }
        if (call.method_name() == "hideToTray") {
          HideToTray();
          result->Success();
          return;
        }
        result->NotImplemented();
      });
}

void FlutterWindow::RegisterCredentialChannel() {
  credential_channel_ =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          flutter_controller_->engine()->messenger(),
          "sagopalgo/windows_credentials",
          &flutter::StandardMethodCodec::GetInstance());
  credential_channel_->SetMethodCallHandler(
      [](const auto& call, auto result) {
        const auto* arguments =
            std::get_if<flutter::EncodableMap>(call.arguments());
        if (arguments == nullptr) {
          result->Error("INVALID_ARGUMENT", "Credential arguments missing");
          return;
        }

        const std::wstring target =
            Utf16FromUtf8(StringArgument(*arguments, "target"));
        if (target.empty() || !IsSagoPalgoCredentialTarget(target)) {
          result->Error("INVALID_TARGET", "Credential target is not allowed");
          return;
        }

        if (call.method_name() == "read") {
          PCREDENTIALW credential = nullptr;
          if (!CredReadW(target.c_str(), CRED_TYPE_GENERIC, 0, &credential)) {
            const DWORD error = GetLastError();
            if (error == ERROR_NOT_FOUND) {
              result->Success(flutter::EncodableValue());
            } else {
              result->Error("CREDENTIAL_READ_FAILED",
                            WindowsErrorMessage("CredReadW", error));
            }
            return;
          }

          const DWORD blob_size = credential->CredentialBlobSize;
          if (blob_size % sizeof(wchar_t) != 0) {
            CredFree(credential);
            result->Error("INVALID_CREDENTIAL", "Credential data is invalid");
            return;
          }
          const auto* blob =
              reinterpret_cast<const wchar_t*>(credential->CredentialBlob);
          const std::wstring value(blob, blob_size / sizeof(wchar_t));
          const std::string converted = Utf8FromUtf16(value);
          CredFree(credential);
          result->Success(flutter::EncodableValue(converted));
          return;
        }

        if (call.method_name() == "write") {
          const std::wstring value =
              Utf16FromUtf8(StringArgument(*arguments, "value"));
          if (value.empty()) {
            result->Error("INVALID_ARGUMENT", "Credential value is empty");
            return;
          }
          wchar_t username[] = L"SagoPalgo local user";
          CREDENTIALW credential{};
          credential.Type = CRED_TYPE_GENERIC;
          credential.TargetName = const_cast<LPWSTR>(target.c_str());
          credential.CredentialBlobSize =
              static_cast<DWORD>(value.size() * sizeof(wchar_t));
          credential.CredentialBlob = reinterpret_cast<LPBYTE>(
              const_cast<wchar_t*>(value.data()));
          credential.Persist = CRED_PERSIST_LOCAL_MACHINE;
          credential.UserName = username;
          if (!CredWriteW(&credential, 0)) {
            const DWORD error = GetLastError();
            result->Error("CREDENTIAL_WRITE_FAILED",
                          WindowsErrorMessage("CredWriteW", error));
            return;
          }
          result->Success();
          return;
        }

        if (call.method_name() == "delete") {
          if (!CredDeleteW(target.c_str(), CRED_TYPE_GENERIC, 0)) {
            const DWORD error = GetLastError();
            if (error != ERROR_NOT_FOUND) {
              result->Error("CREDENTIAL_DELETE_FAILED",
                            WindowsErrorMessage("CredDeleteW", error));
              return;
            }
          }
          result->Success();
          return;
        }

        result->NotImplemented();
      });
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
  wcscpy_s(notification_icon_.szTip, L"SagoPalgo");
  notification_icon_added_ =
      Shell_NotifyIconW(NIM_ADD, &notification_icon_) == TRUE;
  if (notification_icon_added_) {
    notification_icon_.uVersion = NOTIFYICON_VERSION_4;
    Shell_NotifyIconW(NIM_SETVERSION, &notification_icon_);
  }
  return notification_icon_added_;
}

void FlutterWindow::EnterMiniMode() {
  HWND window = GetHandle();
  if (window == nullptr) {
    return;
  }
  if (!mini_mode_) {
    normal_bounds_saved_ = GetWindowRect(window, &normal_bounds_) == TRUE;
  }

  const UINT dpi = GetDpiForWindow(window);
  const int width = MulDiv(420, dpi, 96);
  const int height = MulDiv(600, dpi, 96);
  HMONITOR monitor = MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST);
  MONITORINFO monitor_info{};
  monitor_info.cbSize = sizeof(MONITORINFO);
  GetMonitorInfoW(monitor, &monitor_info);
  const int x = monitor_info.rcWork.right - width - MulDiv(16, dpi, 96);
  const int y = monitor_info.rcWork.top + MulDiv(16, dpi, 96);

  SetWindowPos(window, HWND_TOPMOST, x, y, width, height,
               SWP_SHOWWINDOW | SWP_FRAMECHANGED);
  SetForegroundWindow(window);
  mini_mode_ = true;
}

void FlutterWindow::ShowDashboardWindow() {
  HWND window = GetHandle();
  if (window == nullptr) {
    return;
  }

  if (normal_bounds_saved_) {
    SetWindowPos(window, HWND_NOTOPMOST, normal_bounds_.left,
                 normal_bounds_.top,
                 normal_bounds_.right - normal_bounds_.left,
                 normal_bounds_.bottom - normal_bounds_.top,
                 SWP_SHOWWINDOW | SWP_FRAMECHANGED);
  } else {
    SetWindowPos(window, HWND_NOTOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
  }
  ShowWindow(window, SW_RESTORE);
  SetForegroundWindow(window);
  mini_mode_ = false;
}

void FlutterWindow::HideToTray() {
  HWND window = GetHandle();
  if (window != nullptr) {
    ShowWindow(window, SW_HIDE);
  }
}

void FlutterWindow::SendTrayAction(const std::string& action) {
  if (window_control_channel_) {
    window_control_channel_->InvokeMethod(
        "trayAction", std::make_unique<flutter::EncodableValue>(action));
  }
}

void FlutterWindow::ShowTrayMenu() {
  HMENU menu = CreatePopupMenu();
  if (menu == nullptr) {
    return;
  }
  AppendMenuW(menu, MF_STRING, kTrayShowDashboard,
              L"\uB300\uC2DC\uBCF4\uB4DC \uC5F4\uAE30");
  AppendMenuW(menu, MF_STRING, kTrayMiniMode,
              L"\uBBF8\uB2C8 \uC704\uC82F");
  AppendMenuW(menu, MF_STRING, kTrayRefresh,
              L"\uC0C8\uB85C\uACE0\uCE68");
  AppendMenuW(menu, MF_STRING, kTraySettings, L"\uC124\uC815");
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  AppendMenuW(menu, MF_STRING, kTrayExit, L"\uC885\uB8CC");

  POINT cursor{};
  GetCursorPos(&cursor);
  SetForegroundWindow(GetHandle());
  const UINT command = TrackPopupMenu(
      menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
      cursor.x, cursor.y, 0, GetHandle(), nullptr);
  PostMessage(GetHandle(), WM_NULL, 0, 0);
  DestroyMenu(menu);

  switch (command) {
    case kTrayShowDashboard:
      ShowDashboardWindow();
      SendTrayAction("showDashboard");
      break;
    case kTrayMiniMode:
      EnterMiniMode();
      SendTrayAction("miniMode");
      break;
    case kTrayRefresh:
      SendTrayAction("refresh");
      break;
    case kTraySettings:
      ShowDashboardWindow();
      SendTrayAction("settings");
      break;
    case kTrayExit:
      exiting_ = true;
      Destroy();
      break;
  }
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
    case WM_CLOSE:
      if (!exiting_) {
        HideToTray();
        return 0;
      }
      break;
    case kNotificationCallbackMessage: {
      const UINT event = LOWORD(lparam);
      if (event == WM_CONTEXTMENU || event == WM_RBUTTONUP) {
        ShowTrayMenu();
        return 0;
      }
      if (event == WM_LBUTTONDBLCLK || event == NIN_KEYSELECT) {
        ShowDashboardWindow();
        SendTrayAction("showDashboard");
        return 0;
      }
      break;
    }
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}
