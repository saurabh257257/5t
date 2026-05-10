# 5T Trading Bot - Android App

Real-time monitoring app for your trading bot.

## Features

✅ **Real-time Sensex Monitoring** - Live price updates
✅ **Daily Configuration** - Set support, resistance, lot size
✅ **Active Trades Display** - See current positions
✅ **Trade History** - View past trades and P&L
✅ **Status Dashboard** - Bot health and performance
✅ **WebSocket Integration** - Real-time updates
✅ **Simple UI** - Easy to use while trading

## Screenshots

```
┌─────────────────┐
│  SENSEX: 75432  │
│    Support: 74500
│    Resistance: 76500
│    Lot Size: 1
│
│  [START] [STOP]
│
│ Active Trades: 2
│ Total P&L: +1200
│
│ ┌──────────────┐
│ │ CALL | 74000 │
│ │ Entry: 75500 │
│ │ P&L: +450    │
│ └──────────────┘
│
│ [HISTORY] [SETTINGS]
└─────────────────┘
```

## Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/saurabh257257/5t.git
cd 5t/android-app
```

### 2. Open in Android Studio
- Download Android Studio: https://developer.android.com/studio
- Open project: `File → Open → 5t/android-app`
- Wait for Gradle sync

### 3. Configure Server URL
Edit `app/src/main/java/com/example/tradingbot/network/ApiClient.kt`:

```kotlin
object ApiClient {
    private const val BASE_URL = "http://YOUR_DROPLET_IP:3000"
    
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
}
```

Replace `YOUR_DROPLET_IP` with your actual Droplet IP!

### 4. Add Dependencies
Already in `build.gradle`:
```gradle
// Retrofit for API calls
implementation 'com.squareup.retrofit2:retrofit:2.9.0'
implementation 'com.squareup.retrofit2:converter-gson:2.9.0'

// OkHttp for logging
implementation 'com.squareup.okhttp3:logging-interceptor:4.10.0'

// Socket.io for real-time updates
implementation 'io.socket:socket.io-client:2.1.0'

// Material Design UI
implementation 'com.google.android.material:material:1.5.0'
```

### 5. Run on Device/Emulator
- Connect Android phone via USB (or use emulator)
- Click **Run** button (Shift + F10)
- App opens on your device

---

## App Structure

```
android-app/
├── app/src/main/
│   ├── java/com/example/tradingbot/
│   │   ├── activities/
│   │   │   ├── MainActivity.kt          # Main screen
│   │   │   ├── SettingsActivity.kt      # Config screen
│   │   │   └── HistoryActivity.kt       # Trade history
│   │   ├── models/
│   │   │   ├── Trade.kt                 # Trade data class
│   │   │   └── Status.kt                # Status data class
│   │   ├── network/
│   │   │   ├── ApiClient.kt             # API configuration
│   │   │   ├── ApiService.kt            # API endpoints
│   │   │   └── SocketManager.kt         # WebSocket connection
│   │   ├── utils/
│   │   │   └── Preferences.kt           # SharedPreferences
│   │   └── App.kt                       # Application class
│   ├── res/
│   │   ├── layout/
│   │   │   ├── activity_main.xml
│   │   │   ├── activity_settings.xml
│   │   │   └── item_trade.xml
│   │   ├── values/
│   │   │   └── colors.xml
│   │   └── drawables/
│   └── AndroidManifest.xml
└── build.gradle
```

---

## API Integration

### Connect to Server

```kotlin
// In MainActivity.kt

class MainActivity : AppCompatActivity() {
    private lateinit var apiService: ApiService
    private lateinit var socket: Socket
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Initialize API client
        apiService = ApiClient.getApiService()
        
        // Connect WebSocket
        connectWebSocket()
        
        // Fetch current status
        fetchStatus()
        
        // Setup button listeners
        setupListeners()
    }
    
    private fun connectWebSocket() {
        try {
            socket = IO.socket("http://YOUR_DROPLET_IP:3000")
            
            socket.on("status") { args ->
                val status = args[0] as JSONObject
                updateUI(status)
            }
            
            socket.on("trade") { args ->
                val trade = args[0] as JSONObject
                showNewTrade(trade)
            }
            
            socket.on("trade_closed") { args ->
                val closedTrade = args[0] as JSONObject
                showTradeClose(closedTrade)
            }
            
            socket.connect()
        } catch (e: Exception) {
            showError("Connection failed: ${e.message}")
        }
    }
    
    private fun fetchStatus() {
        apiService.getStatus().enqueue(object : Callback<Status> {
            override fun onResponse(call: Call<Status>, response: Response<Status>) {
                if (response.isSuccessful) {
                    updateUI(response.body())
                }
            }
            
            override fun onFailure(call: Call<Status>, t: Throwable) {
                showError("Failed: ${t.message}")
            }
        })
    }
    
    private fun updateUI(status: Status) {
        findViewById<TextView>(R.id.sensex_price).text = "$${status.sensex}"
        findViewById<TextView>(R.id.support_level).text = "Support: ${status.support}"
        findViewById<TextView>(R.id.resistance_level).text = "Resistance: ${status.resistance}"
        findViewById<TextView>(R.id.active_trades).text = "Active: ${status.activeTrades}"
    }
}
```

---

## Main Screen UI

### Layout (activity_main.xml)

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="16dp">

    <!-- Sensex Price Card -->
    <MaterialCardView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginBottom="16dp">
        
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:padding="16dp">
            
            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="SENSEX"
                android:textSize="14sp"
                android:textColor="#666666" />
            
            <TextView
                android:id="@+id/sensex_price"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="75,432.50"
                android:textSize="32sp"
                android:textStyle="bold"
                android:textColor="#000000" />
        </LinearLayout>
    </MaterialCardView>

    <!-- Settings Card -->
    <MaterialCardView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginBottom="16dp">
        
        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:padding="16dp">
            
            <TextView
                android:id="@+id/support_level"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="Support: 74,500"
                android:textSize="16sp"
                android:layout_marginBottom="8dp" />
            
            <TextView
                android:id="@+id/resistance_level"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="Resistance: 76,500"
                android:textSize="16sp"
                android:layout_marginBottom="8dp" />
            
            <TextView
                android:id="@+id/active_trades"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="Active Trades: 0"
                android:textSize="16sp" />
        </LinearLayout>
    </MaterialCardView>

    <!-- Control Buttons -->
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:layout_marginBottom="16dp">
        
        <Button
            android:id="@+id/start_button"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="START"
            android:layout_marginEnd="8dp" />
        
        <Button
            android:id="@+id/stop_button"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="STOP"
            android:layout_marginStart="8dp" />
    </LinearLayout>

    <!-- Trades RecyclerView -->
    <RecyclerView
        android:id="@+id/trades_list"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1" />

    <!-- Bottom Navigation -->
    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal">
        
        <Button
            android:id="@+id/settings_button"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="Settings"
            android:layout_marginEnd="8dp" />
        
        <Button
            android:id="@+id/history_button"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="History"
            android:layout_marginStart="8dp" />
    </LinearLayout>
</LinearLayout>
```

---

## Settings Screen

```kotlin
class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        
        val supportInput = findViewById<EditText>(R.id.support_input)
        val resistanceInput = findViewById<EditText>(R.id.resistance_input)
        val lotSizeInput = findViewById<EditText>(R.id.lot_size_input)
        val saveButton = findViewById<Button>(R.id.save_button)
        
        // Load saved settings
        val prefs = getSharedPreferences("bot_settings", MODE_PRIVATE)
        supportInput.setText(prefs.getString("support", "74500"))
        resistanceInput.setText(prefs.getString("resistance", "76500"))
        lotSizeInput.setText(prefs.getString("lotSize", "1"))
        
        // Save settings
        saveButton.setOnClickListener {
            val settings = mapOf(
                "support" to supportInput.text.toString().toDouble(),
                "resistance" to resistanceInput.text.toString().toDouble(),
                "lotSize" to lotSizeInput.text.toString().toInt(),
                "authKey" to "daily_key"
            )
            
            ApiClient.getApiService().updateSettings(settings)
                .enqueue(object : Callback<Any> {
                    override fun onResponse(call: Call<Any>, response: Response<Any>) {
                        Toast.makeText(this@SettingsActivity, "Settings saved!", Toast.LENGTH_SHORT).show()
                        finish()
                    }
                    
                    override fun onFailure(call: Call<Any>, t: Throwable) {
                        Toast.makeText(this@SettingsActivity, "Error: ${t.message}", Toast.LENGTH_SHORT).show()
                    }
                })
        }
    }
}
```

---

## Permissions Required

Add to `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

---

## Building the APK

### For Testing
```bash
# Connect device or open emulator
# Click Run button in Android Studio
# APK installs and runs on device
```

### For Production
```bash
# Build menu → Build Bundle(s) / APK(s) → Build APK(s)
# Find APK at: android-app/app/release/app-release.apk
```

---

## Troubleshooting

### App Crashes on Launch?
- Check server URL is correct
- Verify Droplet is running
- Check phone internet connection
- Review logcat output

### No Real-Time Updates?
- Check WebSocket connection
- Verify firewall allows port 3000
- Restart app

### Can't Connect to Server?
- Verify Droplet IP in code
- Check firewall settings
- SSH to server: `curl http://localhost:3000`

---

## Next Steps

1. ✅ Clone repository
2. ✅ Update server URL
3. ✅ Run app on device
4. ✅ Configure support/resistance
5. ✅ Start trading!

---

For help, check:
- Server logs: `ssh root@YOUR_IP && pm2 logs`
- App logcat: Android Studio → Logcat
- GitHub Issues: https://github.com/saurabh257257/5t/issues

---

**Happy Trading! 🚀📱**
