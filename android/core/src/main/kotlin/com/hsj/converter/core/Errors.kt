package com.hsj.converter.core

class HsjException(message: String, cause: Throwable? = null) : Exception(message, cause)

class ConversionCancelledException : Exception("转换已取消")

class InsufficientStorageException(message: String) : Exception(message)
