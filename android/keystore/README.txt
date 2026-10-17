本目录包含 Android release 签名密钥。

- hsj-release.jks + keystore.properties 是本地签名凭据，请勿公开或提交到公共仓库。
- 后续更新 APK 必须继续使用同一密钥，否则 Android 会拒绝覆盖安装。
- 如果丢失密钥，已安装用户需要先卸载旧版才能安装新签名版本。
