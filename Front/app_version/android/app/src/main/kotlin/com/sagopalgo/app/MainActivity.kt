package com.sagopalgo.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Flutter 엔진을 Android Activity로 띄우는 앱의 진입점입니다.
 *
 * 이 클래스의 package 경로는 android/app/build.gradle.kts의 applicationId/namespace와 맞춰 관리합니다.
 * Google/Naver OAuth에서 Android 패키지명을 검증할 때도 같은 값인 com.sagopalgo.app을 기준으로 등록합니다.
 */
class MainActivity : FlutterActivity() {
    private var pendingNaverAuthorizationResult: MethodChannel.Result? = null
    private var expectedNaverRedirectUri: Uri? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleNaverRedirect(intent)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, NAVER_LOGIN_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "authorize" -> authorizeWithNaver(call, result)
                    else -> result.notImplemented()
                }
            }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNaverRedirect(intent)
    }

    private fun authorizeWithNaver(call: MethodCall, result: MethodChannel.Result) {
        if (pendingNaverAuthorizationResult != null) {
            result.error("NAVER_LOGIN_IN_PROGRESS", "Naver 로그인이 이미 진행 중입니다.", null)
            return
        }

        val authorizationUrl = call.argument<String>("authorizationUrl")
        val redirectUri = call.argument<String>("redirectUri")
        if (authorizationUrl.isNullOrBlank() || redirectUri.isNullOrBlank()) {
            result.error(
                "NAVER_CONFIG_MISSING",
                "Naver 로그인 URL 또는 redirect URI가 설정되어 있지 않습니다.",
                null,
            )
            return
        }

        pendingNaverAuthorizationResult = result
        expectedNaverRedirectUri = Uri.parse(redirectUri)
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(authorizationUrl)))
        } catch (exception: ActivityNotFoundException) {
            pendingNaverAuthorizationResult = null
            expectedNaverRedirectUri = null
            result.error(
                "NAVER_BROWSER_NOT_FOUND",
                "Naver 로그인 화면을 열 브라우저를 찾지 못했습니다.",
                null,
            )
        }
    }

    private fun handleNaverRedirect(intent: Intent?) {
        val data = intent?.data ?: return
        val expectedRedirectUri = expectedNaverRedirectUri ?: return
        if (!matchesExpectedRedirect(data, expectedRedirectUri)) {
            return
        }

        val pendingResult = pendingNaverAuthorizationResult
        pendingNaverAuthorizationResult = null
        expectedNaverRedirectUri = null

        val error = data.getQueryParameter("error")
        if (!error.isNullOrBlank()) {
            pendingResult?.error(
                error,
                data.getQueryParameter("error_description") ?: "Naver 로그인이 취소되었거나 실패했습니다.",
                null,
            )
            return
        }

        pendingResult?.success(
            mapOf(
                "code" to data.getQueryParameter("code").orEmpty(),
                "state" to data.getQueryParameter("state").orEmpty(),
            ),
        )
    }

    private fun matchesExpectedRedirect(actual: Uri, expected: Uri): Boolean {
        return actual.scheme == expected.scheme &&
            actual.host == expected.host &&
            actual.path == expected.path
    }

    companion object {
        private const val NAVER_LOGIN_CHANNEL = "com.sagopalgo.app/naver_login"
    }
}
