#ifndef RUNNER_FLUTTER_WINDOW_H_
#define RUNNER_FLUTTER_WINDOW_H_

#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <flutter/method_channel.h>

#include <memory>

#include "win32_window.h"

// A window that does nothing but host a Flutter view.
class FlutterWindow : public Win32Window {
 public:
  // Creates a new FlutterWindow hosting a Flutter view running |project|.
  explicit FlutterWindow(const flutter::DartProject& project);
  virtual ~FlutterWindow();

 protected:
  // Win32Window:
  bool OnCreate() override;
  void OnDestroy() override;
  LRESULT MessageHandler(HWND window, UINT const message, WPARAM const wparam,
                         LPARAM const lparam) noexcept override;

 private:
  // The project to run.
  flutter::DartProject project_;

  // The Flutter instance hosted by this window.
  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;

  // Bridges Flutter notification requests to the Windows notification area.
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>>
      notification_channel_;
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>>
      credential_channel_;
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>>
      window_control_channel_;
  NOTIFYICONDATAW notification_icon_{};
  bool notification_icon_added_ = false;
  bool mini_mode_ = false;
  bool exiting_ = false;
  bool normal_bounds_saved_ = false;
  RECT normal_bounds_{};

  void RegisterNotificationChannel();
  void RegisterCredentialChannel();
  void RegisterWindowControlChannel();
  bool InitializeNotificationIcon();
  bool ShowNotification(const std::string& title, const std::string& body);
  void EnterMiniMode();
  void ShowDashboardWindow();
  void HideToTray();
  void ShowTrayMenu();
  void SendTrayAction(const std::string& action);
};

#endif  // RUNNER_FLUTTER_WINDOW_H_
