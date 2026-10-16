import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// the Oros server (its /api/login gives the token every call carries: Auth.kt, Player 0.0.15) and the feedback service
// (tools/feedback/server.py: GET me = the account's brawler role (Player 0.0.36), the notes, the Brawler app's builds).
// -PorosBase=http://10.0.2.2:8900/ -PfeedbackBase=http://10.0.2.2:8921/ [-PromBase=...] : a proof build against local
// services (cleartext HTTP allowed only then)
val orosBase = (project.findProperty("orosBase") as String?) ?: "https://canneji.duckdns.org/oros/"
val feedbackBase = (project.findProperty("feedbackBase") as String?) ?: "https://canneji.duckdns.org/brawler/feedback/"
val romBase = (project.findProperty("romBase") as String?) ?: "https://canneji.duckdns.org/brawler/download/"

android {
    namespace = "com.neoscan.player"
    compileSdk = 36
    ndkVersion = "30.0.16248370"
    defaultConfig {
        minSdk = 26
        targetSdk = 36
        versionCode = 43
        versionName = "0.0.43"
        // a test build of the self-update (PlayerUpdate.kt): ./gradlew assembleDevDebug -PplayerCode=22 -PplayerName=0.0.22
        (project.findProperty("playerCode") as String?)?.let { versionCode = it.toInt() }
        (project.findProperty("playerName") as String?)?.let { versionName = it }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        buildConfigField("String", "AUTH_URL", "\"$orosBase\"")
        buildConfigField("String", "FEEDBACK_URL", "\"$feedbackBase\"")
    }
    externalNativeBuild { ndkBuild { path = file("src/main/cpp/Android.mk") } }
    // TWO APPS, ONE CODE BASE (docs/feedback.md "Roles and the two apps"), both behind an Oros login with a brawler role:
    //  - dev ("Brawler Dev", com.neoscan.player, the house Player as before): brawler admins only (Oros tag
    //    brawler_admin). The Character lab / Fighter Lab, the Assembly WebView + JS bridge, the live configs and pack
    //    swaps pushed into the running game: src/dev, compiled into this flavor only. Builds from /brawler/download/
    //    (admins), its app updates from player.json there. Signed with the build machine's debug key, as every house
    //    Player so far.
    //  - brawler ("Brawler", com.neoscan.brawler, for testers; an admin may sign in too and gets the same app): the game,
    //    the pad, the Feedback button, the builds up to the account's allowed one (share/latest.json). src/brawler: inert
    //    stubs of the lab and the Assembly, the icon, a manifest without the settings page. Its app updates: GET me's
    //    app {version, code, url (24 h ticket), size, sha256}. Release: not debuggable, no minify / obfuscation /
    //    packer, signed v1 + v2 + v3 with its own key /data/brawler-share/shared-release.jks (SHARE_SIGNING = its
    //    properties file; never the Oros key), so an update installs over the installed app only with that key.
    //  BOTH (0.0.42, one path: src/main PlayerUpdate.kt): the app downloads its own update (progress, size + sha256
    //  checked) and installs it through a PackageInstaller session (REQUEST_INSTALL_PACKAGES, the Status / Restart
    //  receivers, POST_NOTIFICATIONS); the first time the user turns on "Install unknown apps" for it (Android's screen,
    //  opened with one line). May be flagged by antivirus apps (Bruno accepts that). The Brawler app keeps the ticket
    //  link as a fallback in the browser.
    //    ./gradlew assembleBrawlerRelease -> app/build/outputs/apk/brawler/release/app-brawler-release.apk
    val shareSigning = file(System.getenv("SHARE_SIGNING") ?: "/data/brawler-share/signing.properties")
    signingConfigs {
        if (shareSigning.exists()) create("brawler") {
            val p = Properties().apply { shareSigning.inputStream().use { load(it) } }
            storeFile = file(p.getProperty("storeFile")); storePassword = p.getProperty("storePassword")
            keyAlias = p.getProperty("keyAlias"); keyPassword = p.getProperty("keyPassword")
            enableV1Signing = true; enableV2Signing = true; enableV3Signing = true
        }
    }
    flavorDimensions += "app"
    productFlavors {
        create("dev") {
            dimension = "app"
            applicationId = "com.neoscan.player"
            buildConfigField("boolean", "DEV", "true")
            // the dev builds (examples/brawler make publish-vps): brawler admins only
            buildConfigField("String", "ROM_URL", "\"$romBase\"")
            // the web Lab (tools/brawler/chainlab): the Assembly page the Character lab shows (Assembly.kt, Player 0.0.32)
            buildConfigField("String", "LAB_WEB_URL", "\"https://canneji.duckdns.org/brawler-lab/\"")
            manifestPlaceholders["appLabel"] = "Brawler Dev"
            signingConfig = signingConfigs.getByName("debug")
        }
        create("brawler") {
            dimension = "app"
            applicationId = "com.neoscan.brawler"
            buildConfigField("boolean", "DEV", "false")
            buildConfigField("String", "ROM_URL", "\"${feedbackBase}share/\"")   // the account's allowed build
            buildConfigField("String", "LAB_WEB_URL", "\"\"")
            manifestPlaceholders["appLabel"] = "Brawler"
            manifestPlaceholders["cleartext"] = (orosBase.startsWith("http:") || feedbackBase.startsWith("http:")).toString()
            signingConfig = signingConfigs.findByName("brawler")
        }
    }
    buildTypes {
        release { isMinifyEnabled = false; isDebuggable = false; isJniDebuggable = false }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += listOf("zip", "neo") }
    buildFeatures { buildConfig = true }
}
