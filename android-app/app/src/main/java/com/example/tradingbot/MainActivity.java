package com.example.tradingbot;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.EditText;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import okhttp3.*;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class MainActivity extends AppCompatActivity {
    private TextView statusText;
    private EditText supportInput, resistanceInput, lotInput;
    private Button settingsBtn, startBtn, stopBtn, statusBtn;
    private String serverUrl = "http://143.244.140.57:3000";
    private OkHttpClient httpClient = new OkHttpClient();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        statusText = findViewById(R.id.statusText);
        supportInput = findViewById(R.id.supportInput);
        resistanceInput = findViewById(R.id.resistanceInput);
        lotInput = findViewById(R.id.lotInput);
        settingsBtn = findViewById(R.id.settingsBtn);
        startBtn = findViewById(R.id.startBtn);
        stopBtn = findViewById(R.id.stopBtn);
        statusBtn = findViewById(R.id.statusBtn);

        statusBtn.setOnClickListener(v -> fetchStatus());
        settingsBtn.setOnClickListener(v -> updateSettings());
        startBtn.setOnClickListener(v -> startTrading());
        stopBtn.setOnClickListener(v -> stopTrading());

        fetchStatus();
    }

    private void fetchStatus() {
        new Thread(() -> {
            try {
                Request request = new Request.Builder()
                        .url(serverUrl + "/api/status")
                        .get()
                        .build();

                Response response = httpClient.newCall(request).execute();
                String body = response.body().string();
                JsonObject json = JsonParser.parseString(body).getAsJsonObject();

                runOnUiThread(() -> {
                    statusText.setText("Status: " + json.get("status").getAsString() +
                            "\nSensex: " + json.get("sensex").getAsDouble() +
                            "\nSupport: " + json.get("support").getAsInt() +
                            "\nResistance: " + json.get("resistance").getAsInt() +
                            "\nActive Trades: " + json.get("activeTrades").getAsInt());
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void updateSettings() {
        new Thread(() -> {
            try {
                JsonObject json = new JsonObject();
                json.addProperty("support", Integer.parseInt(supportInput.getText().toString()));
                json.addProperty("resistance", Integer.parseInt(resistanceInput.getText().toString()));
                json.addProperty("lotSize", Integer.parseInt(lotInput.getText().toString()));

                RequestBody body = RequestBody.create(json.toString(), MediaType.parse("application/json"));
                Request request = new Request.Builder()
                        .url(serverUrl + "/api/settings")
                        .post(body)
                        .build();

                Response response = httpClient.newCall(request).execute();
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Settings updated!", Toast.LENGTH_SHORT).show();
                    fetchStatus();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void startTrading() {
        new Thread(() -> {
            try {
                Request request = new Request.Builder()
                        .url(serverUrl + "/api/start")
                        .post(RequestBody.create("", MediaType.parse("application/json")))
                        .build();

                httpClient.newCall(request).execute();
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Trading started!", Toast.LENGTH_SHORT).show();
                    fetchStatus();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void stopTrading() {
        new Thread(() -> {
            try {
                Request request = new Request.Builder()
                        .url(serverUrl + "/api/stop")
                        .post(RequestBody.create("", MediaType.parse("application/json")))
                        .build();

                httpClient.newCall(request).execute();
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Trading stopped!", Toast.LENGTH_SHORT).show();
                    fetchStatus();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }
}
