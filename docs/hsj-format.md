# 画世界Pro `.hsj` 格式逆向笔记

对象：画世界Pro Android 3.4.6（包名 `net.huanci.hsjpro`）。
本文中的偏移均为十进制或明确标注的十六进制，多字节整数默认**大端序**。

## 1. 外层：ZIP

`.hsj` 是一个普通 ZIP。当前版本中通常只有一个条目：

```
0        ← 实际的草稿容器（未压缩或 deflate 均可）
```

读取时应对 ZIP 中所有条目做魔数检测，而不是写死文件名。

## 2. 内层容器

文件 `0` 的结构：

| 偏移 | 长度 | 内容 |
|---:|---:|---|
| 0x00 | 8 | 魔数 ASCII `8E9E23DF` |
| 0x08 | 4 | int32 版本号（3.4.6 导出为 `41`） |
| 0x0C | 8 | int64 文件总长度（等于内层文件字节数） |
| 0x14 | 8 | int64 文件索引（footer）偏移 |
| 0x1C | 8 | int64 文件索引长度 |
| 0x24 | 164 | 零填充 |
| 0xC8 | … | 数据区：各草稿文件首尾相接 |
| footer_offset | footer_len | `ExportDraftInfo` protobuf |

APK 中的 `DraftExpImpManager` 导入时可看到其校验逻辑：

```java
if (file.length() < 200) error;
read magic(8); readInt(); // version <= 41
readLong();               // total size == file length
long footerOffset = readLong();
long footerLen = readLong();
seek(footerOffset); read(footerBytes);
ExportDraftInfo info = ExportDraftInfo.parseFrom(footerBytes);
```

## 3. Footer：ExportDraftInfo

protobuf（proto3）消息，本工具用到的字段：

| 字段号 | 类型 | 含义 |
|---:|---|---|
| 1 | string | 草稿文件夹名，如 `HuaShiJiePRO_d693...` |
| 2 | string | 时间戳（毫秒字符串） |
| 12 | repeated DraftFileInfo | 文件索引 |
| 37 | string | 存储位置，如 `hsj_main_sdcard` |

`DraftFileInfo`：

| 字段号 | 类型 | 含义 |
|---:|---|---|
| 1 | string | 文件相对路径，如 `/layers/<uuid>` |
| 2 | int64 | 文件在容器中的**绝对起始偏移** |
| 3 | int64 | 文件长度 |

注意事项：

- 第一个文件（如 `brush.dat`）的起始偏移是 `200`，正好是数据区起点；
  其内容前 4 字节可能是零，不要把它们误当成容器头。
- 路径以 `/` 开头，统一去掉前导斜杠后使用。

## 4. 草稿文件

常见文件：

| 文件 | 内容 |
|---|---|
| `paint.dat` / `paint_as.dat` | `DrawData` protobuf（图层栈 + 操作历史） |
| `layers/<uuid>` | 单个图层的像素数据 |
| `layers/sellayer` | 选区缓存，不是图层 |
| `photos/<uuid>` | 导入图片/素材缓存（最终像素已栅格化进图层） |
| `brush*.dat` | 画笔定义（与转换无关） |
| `pdata.dat` | 绘画动作历史（与转换无关） |
| `helper` | JSON，如 `{"tmpAutoValid":false,"tmpValid":false,"ver":1}` |
| `cover` | JPEG 封面 |

`paint_as.dat` 是自动保存，通常比 `paint.dat` 新。两者都存在时，本工具选择
“图层数更多”的一个；图层数相同时优先 `paint_as.dat`。

## 5. 图层像素文件 `layers/<uuid>`

### 5.1 文件头

| 偏移 | 长度 | 内容 |
|---:|---:|---|
| 0x00 | 4 | 魔数 `hsj\0` |
| 0x04 | 3 | 版本号（1 或 2） |
| 0x07 | 4 | 画布宽度 |
| 0x0B | 4 | 画布高度 |
| 0x0F | 1 | flags（样本中为 1） |
| 0x10 | 16 | 内容包围盒 x0,y0,x1,y1（4×uint32） |
| 0x20 | 68 | 零填充 |
| 0x64 | 24 | 第 1 个分条的头部（见下） |
| 0x7C | … | 第 1 个分条的压缩数据 |

### 5.2 分条（strip）

从 0x64 开始是重复结构：

```
[24 字节分条头][compressedSize 字节压缩数据]
[24 字节分条头][compressedSize 字节压缩数据]
...
```

24 字节分条头：

| 偏移 | 类型 | 含义 |
|---:|---|---|
| +0 | uint32 | 解压后字节数（= 条带宽 × 条带高 × 4） |
| +4 | uint32 | 压缩数据长度 |
| +8 | uint32 | x（画布左边界） |
| +12 | uint32 | y（**以画布底部为原点**） |
| +16 | uint32 | 条带存储宽度 |
| +20 | uint32 | 条带存储高度 |

坐标与像素方向：

- 分条头里的 `y` 是“底部原点”坐标；放到常见的左上原点画布时：
  `top = canvasHeight - (y + h)`。
- 解压后的像素是 **RGBA8888、straight alpha（非预乘）**；
- 行序是**自下而上**，需要先上下翻转，再贴到 `(x, top)`。
- 一个图层可能被拆成多个横向条带（宽度通常受约 5.5 MB / 64 MB 缓冲区限制）。
  最后一条的宽度可能与前几条不同，应以“解压字节数 ÷ (h×4)”为准。
- 存储条带可能比内容包围盒略大（含画笔/滤镜的边界填充），直接按分条头坐标粘贴即可。

### 5.3 压缩方式

- **版本 1**：LZ4 block（无 frame 头），用 24 字节头中的解压后大小调用
  `LZ4_decompress_safe`。
- **版本 2**：Zstd 帧（魔数 `28 B5 2F FD`，无 content size），压缩数据长度仍由
  24 字节头的第二字段给出，可直接按长度切帧。

样本中版本 1 最多 2 个条带，版本 2 最多 16 个条带。

## 6. DrawData（paint.dat / paint_as.dat）

本工具用到的字段（proto3）：

| 字段号 | 类型 | 含义 |
|---:|---|---|
| 3 | int32 | 背景色（Android ARGB 有符号 int） |
| 4 | int32 | 图层数 |
| 5 | int32 | 画布宽 |
| 6 | int32 | 画布高 |
| 10 | bool | 背景是否隐藏（缺省 false） |
| 20 | map<string, MpLayers> | 图层状态，通常键为 `"0"` |
| 30 | int32 | PPI（常见 600 / 300） |
| 39 | string | 色彩空间，如 `Display P3` |

`MpLayers`：

| 字段号 | 类型 | 含义 |
|---:|---|---|
| 1 | repeated LayerInfo | 图层栈，**自下而上** |

### 6.1 LayerInfo

| 字段号 | 类型 | 含义 |
|---:|---|---|
| 1 | string | 图层 id，对应 `layers/<id>` |
| 2 | float | 不透明度 0..1 |
| 3 | bool | 锁定 |
| 4 | bool | 可见 |
| 5 | enum | 混合模式（见下） |
| 6 | string | imageData（样本为空） |
| 7 | bool | 锁定透明度 |
| 8 | string | 图层名（可能是 GBK 字节） |
| 9 | enum | 剪贴蒙版类型 |
| 10 | int32 | 剪贴组 id |
| 11 | int32 | layerNo（创建/编号，不等于栈顺序） |
| 12 | int32 | mpKey |
| 13 | bool | 是否组 |
| 14 | repeated LayerInfo | 组内子图层 |
| 15 | string | 父组 id |
| 16 | bool | 组是否展开 |
| 17 | int32 | 图层颜色标签 |
| 18/19 | bool | 蒙版创建/停止状态 |
| 20/21 | bool | flipX / flipY |

关键细节：

- **proto3 没有字段 presence**。画世界会把 `visible=true` 显式写入；字段缺失表示
  `false`（隐藏）。因此不能用“缺省 true”去解释。若整个文件中所有图层都没有
  `visible` 字段（更旧版本），本工具才统一按可见处理。
- 中文图层名在部分版本中直接以 **GBK 字节**写入 protobuf `string` 字段。
  解析时应先试 UTF-8，失败再按 GBK 解码。
- 图层名为空时，画世界按默认名显示（“图层 N”），导出文件里可能完全没有名字。

### 6.2 BlendMode

```
0 NORMAL        1 MULTIPLY       2 SCREEN        3 LINEAR_DODGE
4 DARK          5 COLOR_BURN     6 COLOR_DODGE   7 OVERLAY
8 SOFT_LIGHT    9 DIVIDE         10 COLOR        11 LUMINOSITY
12 SATURATION   13 DISSOLVE      14 LINEAR_BURN  15 DARKER_COLOR
16 LIGHTEN      17 LIGHTER_COLOR 18 HARD_LIGHT   19 VIVID_LIGHT
20 LINEAR_LIGHT 21 PIN_LIGHT     22 HARD_MIX     23 DIFFERENCE
24 EXCLUSION    25 SUBTRACT      26 HUE          27 GLOW
28 PASS_THROUGH 29 GROUP_NORMAL
```

样本中 `DARK(4)` 的实际效果等于“变暗 / min(backdrop, source)”。

### 6.3 ClipMaskType

```
0 Mask_NONE
1 MASK_TOP      ← 被剪贴层
2 MASK_MIDDLE   ← 被剪贴层
3 MASK_BOTTOM   ← 剪贴基础层
```

同组中 `MASK_BOTTOM` 是基础层，位于它上方的 `MASK_TOP/MIDDLE` 用基础层的 alpha
进行裁剪。导出样本中一个组的图层是相邻的。

## 7. 逆向方法记录

- `classes*.dex` 使用 `dexdump` 反汇编；
- 字符串混淆为 **StringFog**：`base64 decode` 后逐字节 XOR `hsjproapp`
  （例如 `UDZTNUBcJTY=` → `8E9E23DF`）；
- protobuf 生成的 `FileDescriptorProto` 也被 StringFog 包裹。解密后需按
  UTF-8 解码、再按 Latin-1 编码，才能恢复描述符原始字节；
- 从描述符导出了 `DrawModel.proto`、`LayerAction.proto` 的完整字段与枚举，
  再与导出的二进制样本逐字段对照确认。
- 导出逻辑位于 `net.huanci.hsjpro.managers.DraftExpImpManager`，图层元数据来自
  `DrawData.mpLayers`，图层像素来自 `layers/<id>`。

## 8. 与转换器实现的对应关系

| 格式结构 | 代码位置 |
|---|---|
| ZIP / 容器头 / footer | `hsjconv/__init__.py::load_hsj` |
| protobuf wire 解码 | `hsjconv/__init__.py::_iter_fields` |
| DrawData / LayerInfo | `hsjconv/__init__.py::parse_draw_data` |
| 版本 1 LZ4 分条 | `hsjconv/__init__.py::_iter_lz4_strips` |
| 版本 2 Zstd 分条 | `hsjconv/__init__.py::_iter_zstd_strips` |
| 图层坐标/翻转 | `hsjconv/__init__.py::decode_layer` |
| 混合/剪贴/合成 | `hsjconv/blend.py` |
| PSD 输出 | `hsjconv/psd.py` |
| ORA 输出 | `hsjconv/ora.py` |
