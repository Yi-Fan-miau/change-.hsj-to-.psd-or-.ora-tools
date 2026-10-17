# HSJ Converter — Android

原生 Kotlin + Jetpack Compose 应用，把画世界Pro 的 `.hsj` 多图层草稿转换为
PSD / ORA。

- 最低系统：Android 6.0（minSdk 23）
- 已验证设备：Huawei GRL-AL10，Android 12 / API 31，arm64-v8a
- ABI：arm64-v8a、armeabi-v7a、x86_64

## 功能

- SAF 导入 `.hsj`，显示画布、PPI、色彩空间、图层树和警告；
- PSD / ORA / 两者，可选背景色图层、覆盖已有文件；
- 选择输出文件夹、自定义文件名；
- 前台服务转换，通知栏进度与取消；
- 日志复制/清空、完整日志面板；
- 结果打开/分享；支持从文件管理器“打开方式/分享”接收 `.hsj`；
- 深色现代界面、自适应图标、中文界面。

## 构建

### 依赖

- JDK 21；
- Android SDK：compileSdk 36、build-tools 36.0.0；
- Gradle 8.14.5（仓库不提交 `gradle-wrapper.jar`，可用已安装的 Gradle，
  或先运行 `gradle wrapper` 生成 wrapper）；
- Python + Pillow（用于生成图标）。

### 生成资源与构建

在仓库根目录执行：

```bash
python tools/make_icons.py
python android/tools/make_android_icons.py

cd android
gradle :app:assembleRelease
```

如果使用 Gradle wrapper：

```bash
cd android
gradle wrapper --gradle-version 8.14.5
./gradlew :app:assembleRelease     # Windows: gradlew.bat :app:assembleRelease
```

生成的图标、mipmap PNG、`drawable-nodpi` 图片和 Gradle wrapper jar 默认
被 `.gitignore` 排除，首次构建前必须运行上面的生成脚本。

### 签名

Release 构建需要本地签名文件：

```
android/keystore/hsj-release.jks
android/keystore/keystore.properties
```

`keystore.properties` 格式：

```properties
storeFile=keystore/hsj-release.jks
storePassword=...
keyAlias=hsj
keyPassword=...
```

这两个文件不会被提交。更新已安装 APK 时必须继续使用同一密钥，否则 Android
会拒绝覆盖安装。

### Windows 非 ASCII 路径

AGP 和 JUnit 在含中文的 Windows 路径下可能失败，工程已启用：

- `android.overridePathCheck=true`；
- `core/build.gradle.kts` 在非 ASCII 项目路径下把 core 构建目录放到
  `%TEMP%\hsj-core-build`；
- 推荐通过 ASCII junction 构建：

```bat
mklink /J C:\hsj-android "<project>\android"
cd /d C:\hsj-android
gradle :app:assembleRelease
```

`android/build_release.bat` 会自动创建 junction、生成图标、构建并把 APK 复制到
仓库根目录的 `dist-android/`。

## 测试

### JVM 一致性测试

需要自备样本放到仓库根目录 `samples/`（`*.hsj` 被 `.gitignore` 排除）。

```bash
python android/tools/dump_reference.py
cd android
gradle :core:test -Phsj.samplesDir="../samples"
```

覆盖内容：

- 元数据、图层树、扁平属性与 Python 参考一致；
- 每个图层的 RGBA SHA-256 与 Python 完全一致；
- test47 与 6000×6000 样本的 PSD/ORA 层像素完全一致；
- 合并预览最大差值 1–2 LSB。

### 设备测试

```bash
cd android
gradle :app:assembleDebug :app:assembleDebugAndroidTest

adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk

# 将样本放入 debug 应用的外部目录
adb push ../samples/test47.hsj \
  /sdcard/Android/data/com.hsj.converter.debug/files/test47.hsj

adb shell am instrument -w \
  -e class com.hsj.converter.EngineDeviceTest \
  com.hsj.converter.debug.test/androidx.test.runner.AndroidJUnitRunner
```

## 技术结构

```
core/   纯 Kotlin/JVM：容器、protobuf、图层树、LZ4/Zstd 分条解码、
        映射 RGBA/alpha 表面、合成、PSD PackBits/RLE、ORA PNG/stack.xml
app/    Compose UI、SAF、前台服务、通知、打开/分享、图标
tools/  Python 参考数据生成、Android 图标生成
```

依赖：

- Zstd：`com.github.luben:zstd-jni:1.5.7-12@aar`
- LZ4：`at.yawk.lz4:lz4-java:1.8.1`（`LZ4Factory.safeInstance()`）
- PNG：`ar.com.hjg:pngj:2.1.0`
- Compose / Material3 / AndroidX

R8 必须保留反射与 JNI 类（见 `app/proguard-rules.pro`）：

```proguard
-keep class com.github.luben.zstd.** { *; }
-keep class net.jpountz.** { *; }
-keep class ar.com.hjg.pngj.** { *; }
```

## 已知限制

- 与桌面版一致：只转换当前图层像素；PSD 组扁平化；ORA 剪贴烘焙进 alpha；
  Display P3 不嵌入 ICC；PSD 上限 30000×30000；
- 6000×6000 任务在 app cache 中生成临时文件，建议预留约 1 GB 空间；
- release 版输出先写缓存临时文件，再复制到 SAF；复制阶段失败时可能只留下
  其中一个格式；
- 未上架 Google Play；APK 使用本地 release 密钥签名。

## 验证记录

- `test47.hsj`：设备引擎测试约 5.6 秒；release 版通过 SAF 转换 PSD+ORA
  约 3.3 秒；48 层像素与 Python 参考完全一致；Krita 5.2.13 可打开。
- `图像.hsj`（6000×6000）：设备引擎测试约 22.4 秒；PSD/ORA 层像素一致，
  合并预览最大差 1–2 LSB；Krita 可打开并导出。
