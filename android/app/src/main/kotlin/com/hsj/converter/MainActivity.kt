package com.hsj.converter

import android.content.Intent
import android.net.Uri
import android.util.Log
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.core.content.IntentCompat
import com.hsj.converter.ui.ConverterScreen
import com.hsj.converter.ui.ConverterViewModel
import com.hsj.converter.ui.theme.HsjTheme

class MainActivity : ComponentActivity() {
    private val viewModel: ConverterViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
        setContent {
            HsjTheme {
                ConverterScreen(viewModel)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent == null) return
        Log.i("HSJConverter", "intent action=${intent.action} data=${intent.data}")
        val uri: Uri? = when (intent.action) {
            Intent.ACTION_VIEW -> intent.data
            Intent.ACTION_SEND -> IntentCompat.getParcelableExtra(
                intent, Intent.EXTRA_STREAM, Uri::class.java)
            else -> null
        }
        if (uri != null) {
            viewModel.importUri(uri)
        }
    }
}
