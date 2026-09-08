package com.sagopalgo.app

import io.flutter.embedding.android.FlutterActivity

/**
 * Flutter 엔진을 Android Activity로 띄우는 앱의 진입점입니다.
 *
 * 이 클래스의 package 경로는 android/app/build.gradle.kts의 applicationId/namespace와 맞춰 관리합니다.
 * Google/Naver OAuth에서 Android 패키지명을 검증할 때도 같은 값인 com.sagopalgo.app을 기준으로 등록합니다.
 */
class MainActivity : FlutterActivity()
