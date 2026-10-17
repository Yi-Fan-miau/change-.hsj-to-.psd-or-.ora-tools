package com.hsj.converter.core

object MetadataParser {
    fun parseLayerInfo(buf: ByteArray, depth: Int = 0): LayerInfo {
        if (depth > 64) throw HsjException("图层树嵌套过深")
        val li = LayerInfo()
        val fields = HashMap<Int, ProtoReader.Field>()
        val reader = ProtoReader(buf, 0, buf.size)
        while (true) {
            val field = reader.next() ?: break
            when {
                field.number == 14 && field.wireType == 2 ->
                    li.children += parseLayerInfo(field.bytes!!, depth + 1)
                else -> fields[field.number] = field
            }
        }

        fields[1]?.bytes?.let { li.id = String(it, Charsets.UTF_8) }
        fields[8]?.bytes?.let { li.name = decodeText(it) }
        fields[2]?.bytes?.let { li.opacity = floatLe(it) }
        li.visiblePresent = fields.containsKey(4)
        li.visible = (fields[4]?.varint ?: 0L) != 0L
        li.blendMode = (fields[5]?.varint ?: 0L).toInt()
        li.clipType = (fields[9]?.varint ?: 0L).toInt()
        li.clipGroup = asInt32(fields[10]?.varint ?: 0L)
        li.layerNo = asInt32(fields[11]?.varint ?: 0L)
        li.isGroup = (fields[13]?.varint ?: 0L) != 0L
        li.isLock = (fields[3]?.varint ?: 0L) != 0L
        li.isLockAlpha = (fields[7]?.varint ?: 0L) != 0L
        fields[15]?.bytes?.let { li.parentId = String(it, Charsets.UTF_8) }
        return li
    }

    private fun parseMpLayers(buf: ByteArray): List<LayerInfo> {
        val out = ArrayList<LayerInfo>()
        val reader = ProtoReader(buf, 0, buf.size)
        while (true) {
            val field = reader.next() ?: break
            if (field.number == 1 && field.wireType == 2) {
                out += parseLayerInfo(field.bytes!!)
            }
        }
        return out
    }

    fun parseDrawData(buf: ByteArray): DrawData {
        val data = DrawData()
        val mapLayers = LinkedHashMap<String, List<LayerInfo>>()
        val directLayers = ArrayList<LayerInfo>()

        val reader = ProtoReader(buf, 0, buf.size)
        while (true) {
            val field = reader.next() ?: break
            when {
                field.number == 3 && field.wireType == 0 ->
                    data.bgColor = asInt32(field.varint)
                field.number == 5 && field.wireType == 0 ->
                    data.canvasWidth = field.varint.toInt()
                field.number == 6 && field.wireType == 0 ->
                    data.canvasHeight = field.varint.toInt()
                field.number == 10 && field.wireType == 0 ->
                    data.bgHidden = field.varint != 0L
                field.number == 30 && field.wireType == 0 ->
                    data.ppi = field.varint.toInt().let { if (it == 0) 72 else it }
                field.number == 39 && field.wireType == 2 ->
                    data.colorSpace = String(field.bytes!!, Charsets.UTF_8)
                field.number == 20 && field.wireType == 2 -> {
                    var key = ""
                    var layers: List<LayerInfo> = emptyList()
                    val entry = ProtoReader(field.bytes!!, 0, field.bytes.size)
                    while (true) {
                        val f = entry.next() ?: break
                        when {
                            f.number == 1 && f.wireType == 2 ->
                                key = String(f.bytes!!, Charsets.UTF_8)
                            f.number == 1 && f.wireType == 0 ->
                                key = f.varint.toString()
                            f.number == 2 && f.wireType == 2 ->
                                layers = parseMpLayers(f.bytes!!)
                        }
                    }
                    mapLayers[key] = layers
                }
                field.number == 2 && field.wireType == 2 ->
                    directLayers += parseLayerInfo(field.bytes!!)
            }
        }

        data.layers = when {
            mapLayers.isNotEmpty() -> mapLayers["0"] ?: mapLayers.values.maxByOrNull { it.size } ?: emptyList()
            else -> directLayers
        }

        val all = ArrayList<LayerInfo>()
        fun walk(items: List<LayerInfo>) {
            for (item in items) {
                all += item
                walk(item.children)
            }
        }
        walk(data.layers)
        if (all.isNotEmpty() && all.none { it.visiblePresent }) {
            all.forEach { it.visible = true }
        }

        fun defaultNames(items: List<LayerInfo>) {
            items.forEachIndexed { index, item ->
                if (item.name.isBlank()) item.name = "图层 ${index + 1}"
                defaultNames(item.children)
            }
        }
        defaultNames(data.layers)
        return data
    }
}
