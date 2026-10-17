package com.hsj.converter.core

object LayerTree {
    /** Input and output order are bottom-to-top. */
    fun build(layers: List<LayerInfo>): List<LayerInfo> {
        if (layers.isEmpty()) return emptyList()
        val byId = layers.filter { it.id.isNotEmpty() }.associateBy { it.id }
        val hasParent = layers.any { it.parentId.isNotEmpty() }
        val hasNested = layers.any { it.children.isNotEmpty() }
        if (!hasParent && !hasNested) return layers

        if (hasNested) {
            val childIds = HashSet<String>()
            fun mark(node: LayerInfo) {
                for (child in node.children) {
                    childIds += child.id
                    mark(child)
                }
            }
            layers.filter { it.isGroup }.forEach { mark(it) }
            val roots = layers.filter { it.id !in childIds }
            return roots.ifEmpty { layers }
        }

        val roots = ArrayList<LayerInfo>()
        val childrenMap = LinkedHashMap<String, MutableList<LayerInfo>>()
        for (layer in layers) {
            if (layer.parentId.isNotEmpty() && layer.parentId in byId) {
                childrenMap.getOrPut(layer.parentId) { ArrayList() } += layer
            } else {
                roots += layer
            }
        }
        for (layer in layers) {
            val children = childrenMap[layer.id]
            if (children != null) {
                layer.children.clear()
                layer.children += children
                layer.isGroup = true
            }
        }
        return roots.ifEmpty { layers }
    }

    fun flattenForPsd(
        roots: List<LayerInfo>,
        prefix: String = "",
        parentOpacity: Float = 1f,
        parentVisible: Boolean = true,
    ): List<LeafLayer> {
        val out = ArrayList<LeafLayer>()
        for (layer in roots) {
            if (layer.isGroup) {
                val groupName = layer.name.ifBlank { "组" }
                out += flattenForPsd(
                    layer.children,
                    "$prefix$groupName/",
                    parentOpacity * layer.opacity,
                    parentVisible && layer.visible,
                )
            } else {
                out += LeafLayer(
                    layer = layer,
                    name = prefix + layer.name.ifBlank { "图层" },
                    opacity = parentOpacity * layer.opacity,
                    visible = parentVisible && layer.visible,
                )
            }
        }
        return out
    }

    fun leaves(roots: List<LayerInfo>): List<LayerInfo> = flattenForPsd(roots).map { it.layer }

    fun countLeaves(roots: List<LayerInfo>): Int = leaves(roots).size
}
