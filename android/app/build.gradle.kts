import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.neoscan.player"
    compileSdk = 36
    ndkVersion = "30.0.16248370"
    defaultConfig {
        applicationId = "com.neoscan.player"
        minSdk = 26
        targetSdk = 36
        versionCode = 35
        versionName = "0.0.35"
        // a test build of the self-update (PlayerUpdate.kt): ./gradlew assembleDebug -PplayerCode=22 -PplayerName=0.0.22
        (project.findProperty("playerCode") as String?)?.let { versionCode = it.toInt() }
        (project.findProperty("playerName") as String?)?.let { versionName = it }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        // where builds are published (examples/brawler make publish-vps)
        buildConfigField("String", "ROM_URL", "\"https://canneji.duckdns.org/brawler/download/\"")
        // the Oros server: its /api/login gives the token every call carries (Auth.kt, Player 0.0.15)
        buildConfigField("String", "AUTH_URL", "\"https://canneji.duckdns.org/oros/\"")
        // the web Lab (tools/brawler/chainlab): the Assembly page the Character lab shows (Assembly.kt, Player 0.0.32)
        buildConfigField("String", "LAB_WEB_URL", "\"https://canneji.duckdns.org/brawler-lab/\"")
        buildConfigField("String", "LOGIN_PATH", "\"api/login\"")
        // THE SHARED PLAYER (TODO T2): false = the house Player (Oros accounts, Character lab, self-update)
        buildConfigField("boolean", "SHARED", "false")
    }
    externalNativeBuild { ndkBuild { path = file("src/main/cpp/Android.mk") } }
    // THE SHARED PLAYER (TODO T2, docs/feedback.md "Shared players"): ./gradlew assembleShared -> outputs/apk/shared/
    // app-shared.apk, for players outside the house (Wael, Asenka). The same code; BuildConfig.SHARED switches off the
    // Character lab, the test queue, the decisions, the self-update (src/shared/: a no-op PlayerUpdate, no Assembly
    // WebView; its manifest drops the install permissions and cleartext HTTP); sign-in with a shared account
    // (tools/feedback/server.py share/login), the game = the account's assigned build (share/latest.json). A release
    // build: not debuggable, no minify / obfuscation, signed v1+v2+v3 with its own key (/data/brawler-share/
    // shared-release.jks; SHARE_SIGNING = its properties file; never the Oros key).
    val shareSigning = file(System.getenv("SHARE_SIGNING") ?: "/data/brawler-share/signing.properties")
    signingConfigs {
        if (shareSigning.exists()) create("shared") {
            val p = Properties().apply { shareSigning.inputStream().use { load(it) } }
            storeFile = file(p.getProperty("storeFile")); storePassword = p.getProperty("storePassword")
            keyAlias = p.getProperty("keyAlias"); keyPassword = p.getProperty("keyPassword")
            enableV1Signing = true; enableV2Signing = true; enableV3Signing = true
        }
    }
    buildTypes {
        release { isMinifyEnabled = false; signingConfig = signingConfigs.getByName("debug") }
        create("shared") {
            initWith(getByName("release"))
            isDebuggable = false; isJniDebuggable = false; isMinifyEnabled = false
            applicationIdSuffix = ".shared"
            signingConfig = signingConfigs.findByName("shared")
            buildConfigField("boolean", "SHARED", "true")
            // -PshareBase=http://10.0.2.2:8921/share/ : a proof build against a local service (cleartext allowed only then)
            val base = (project.findProperty("shareBase") as String?) ?: "https://canneji.duckdns.org/brawler/feedback/share/"
            buildConfigField("String", "ROM_URL", "\"$base\"")
            buildConfigField("String", "AUTH_URL", "\"$base\"")
            manifestPlaceholders["shareCleartext"] = base.startsWith("http:").toString()
            buildConfigField("String", "LOGIN_PATH", "\"login\"")
            buildConfigField("String", "LAB_WEB_URL", "\"\"")
            manifestPlaceholders["appLabel"] = "Brawler"
        }
        getByName("debug") { manifestPlaceholders["appLabel"] = "NeoScan Player" }
        getByName("release") { manifestPlaceholders["appLabel"] = "NeoScan Player" }
    }
    // the house-only parts (the APK self-install, the Assembly WebView): src/devtools, in debug + release, not in shared
    sourceSets { getByName("debug").java.srcDir("src/devtools/java"); getByName("release").java.srcDir("src/devtools/java") }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += listOf("zip", "neo") }
    buildFeatures { buildConfig = true }
}
