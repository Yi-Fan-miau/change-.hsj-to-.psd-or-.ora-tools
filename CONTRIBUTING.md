# Contributing

感谢你愿意改进 HSJ Converter。请保持改动小而聚焦，并附上可复现的验证。

## 提交前

- 不要提交 `.hsj` 样本、`画世界Pro.apk`、反编译产物、签名密钥
  （`*.jks` / `keystore.properties`）、本机 `local.properties` 或构建产物。
- 生成图标与安装器图片请用 `tools/make_icons.py`、`tools/make_installer_art.py`。
- Python 代码保持 3.10+ 兼容；Android 代码保持 minSdk 23。
- 修改格式/合成/写入逻辑后，请用 samples 和 psd-tools/Krita 做回归。

## 本地检查

```bash
python -m py_compile hsj2psd.py hsj2psd_gui.py hsjconv/*.py tools/*.py packaging/*.py

# Android core 一致性测试（需要自备 samples/）
python android/tools/dump_reference.py
cd android && gradle :core:test
```

## Pull Request

- 一个 PR 解决一个主题；
- 说明改了什么、为什么、如何验证；
- 如果是 UI 改动，请附截图（不要包含个人草稿或隐私内容）；
- 确认没有把上述敏感/大文件加入提交。
