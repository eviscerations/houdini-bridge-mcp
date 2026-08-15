# houdini-bridge-mcp — セットアップと初回テスト

AIクライアント（例：Claude Desktop）がHoudiniを駆動できるようにツールを配線します。可動部は3つです：

```
MCP client ──stdio──▶ houdini-bridge-mcp.exe (gateway) ──loopback:PORT──▶ executor (armed inside Houdini)
```

ゲートウェイとHoudini内エグゼキューターは、1つの**トークン**、**ポート**、**作業ディレクトリ**を共有します — いずれもGUIが書き込む`~/.houdini-bridge-mcp/arm.json`を単一のソースとします。設定はGUIで一度行うだけで、Houdiniは起動時に自動でarmします。手動のシェルスニペットも、ポート衝突の調整作業も不要です。

---

## 1. 前提条件

- **Houdini 21.0.671**。
- **Rustツールチェーン**（stable） — ゲートウェイのビルドに必要です。
- **Python** — オプションのタイルダウンローダーにのみ必要です。最近のCPythonであれば動作します。唯一の依存関係（`numpy`）は`downloader/requirements.txt`に宣言されています（`pip install -r downloader/requirements.txt`）。中核となるゲートウェイとHoudini内エグゼキューターには、Pythonパッケージは不要です。

## 2. ゲートウェイのビルド

```
cd gateway
cargo build --release
```

1つのバイナリが生成されます：`<PATH_TO_REPO>\gateway\target\release\houdini-bridge-mcp.exe`。これはGUIとヘッドレスMCPゲートウェイの両方を兼ねます — モードは`HMCP_GW_HEADLESS`環境変数で選択されます（未設定 = GUIウィンドウ、`1` = ヘッドレスstdioサーバー）。

## 3. 自動armのHoudiniパッケージのインストール

これは、GUI起動時にエグゼキューターを自動的にarmするHoudini [package](https://www.sidefx.com/docs/houdini/ref/plugins.html)を配置します。

**GUI経由（推奨）：** `houdini-bridge-mcp.exe`を起動し、**Settings → Install Houdini package**を選択します。

**または手動で**、2つの静的パッケージファイルをHoudiniのユーザー設定ディレクトリ（`<HOUDINI_USER_PREF_DIR>`、デフォルトは`%USERPROFILE%\Documents\houdini21.0`）へコピーします：

```
houdini_package/houdini-bridge-mcp.json            →  <HOUDINI_USER_PREF_DIR>/packages/houdini-bridge-mcp.json
houdini_package/houdini-bridge-mcp/scripts/456.py  →  <HOUDINI_USER_PREF_DIR>/houdini-bridge-mcp/scripts/456.py
```

パッケージの`.json`は`packages/`の中に置き、プラグインフォルダはその1つ上、設定ディレクトリのルートに置きます。両ファイルとも配布可能です — 絶対パス、ユーザー名、マシン固有の値は含まれません（動的なものはすべて実行時に`arm.json`から読み込まれます）。

## 4. GUIでの設定

ウィンドウが表示されるよう`HMCP_GW_HEADLESS`を未設定のまま`houdini-bridge-mcp.exe`を起動し、次の手順を行います：

1. **Settings** — **Executor port**と**Session token**を確認します（デフォルトのままで問題ありません。トークンは共有シークレットです）。
2. **Working dir**タブ — **作業ディレクトリのROOT**（プロジェクトのルート。その配下のすべてのサブディレクトリが辿れます）を入力し、**Apply**をクリックします。
3. **Settings**に戻り、**Auto-arm Houdini**をオンにします。

Apply + Auto-armは`~/.houdini-bridge-mcp/arm.json`にマージ書き込みします：

```json
{
  "enabled": true,
  "working_dir": "<WORKING_DIR>",
  "token": "<YOUR_TOKEN>",
  "port": 8765,
  "executor_root": "<abs dir containing the houdini_executor python package>"
}
```

このファイルが唯一の信頼できる情報源（single source of truth）です。GUI、エグゼキューター、ヘッドレスゲートウェイはいずれも`working_dir` / `port` / `token`をここからライブで読み込みます — 作業ディレクトリの変更はApplyするだけで済み、再起動は不要です。

## 5. エグゼキューターのarm

**まずファイアウォールを強化してください。** エグゼキューターのarmは**フェイルクローズ**です — そのループバックポートへのインバウンド接続をブロックするファイアウォールルールがない限り、armを拒否します。同梱のスクリプトを一度だけ実行してください（管理者権限で）：

```
scripts/harden-firewall.ps1              # -Mode loopback (default): loopback-only, single machine
scripts/harden-firewall.ps1 -Mode lan    # allow a studio LAN to reach the executor
```

信頼できる単一マシンには`loopback`（デフォルト）を使用します。`lan`は信頼できるスタジオネットワーク上でのみ使用してください。

続いてHoudiniを起動します。インストールされたパッケージが`arm.json`からエグゼキューターを自動でarmし、コンソールに次が表示されます：

```
[houdini-bridge-mcp] executor armed
```

GUIのステータスピルには、接続されたHoudiniのバージョンとともに**Armed**が表示されます。Pythonシェルのスニペットは不要です。

任意のシェルから確認します：

```
curl.exe http://127.0.0.1:8765/health -H "X-HMCP-Token: <YOUR_TOKEN>"
```

→ `{"ok": true, "service": "houdini-bridge-mcp", ...}`（設定したポートを使用してください）。

## 6. MCPクライアントへの登録

クライアント（例：Claude Desktop — `%APPDATA%\Claude\claude_desktop_config.json`）を、**ヘッドレス**モードのゲートウェイバイナリに向けます。ゲートウェイは`working_dir` / `port` / `token`を`arm.json`から読み込むため、env ブロックにはヘッドレスフラグだけがあれば十分です：

```json
{
  "mcpServers": {
    "houdini-bridge-mcp": {
      "command": "<PATH_TO_REPO>\\gateway\\target\\release\\houdini-bridge-mcp.exe",
      "env": {
        "HMCP_GW_HEADLESS": "1"
      }
    }
  }
}
```

クライアントを完全に終了して再度開きます。新しいチャットに`houdini-bridge-mcp`のツールが現れます。

## 7. 初回テスト

MCPクライアントのチャットから：

1. `scene_info` → ゲートウェイ↔エグゼキューターのリンクを確認します。
2. `import_heightfield(npy="<TILE>.npy", name="terrain", display=true)` → 準備済みのDEMタイルを実際のHoudiniハイトフィールドに変換します。

`npy`パスは作業ディレクトリROOTからの相対パス、またはその内部にあります。各`<TILE>.npy`には、その`<TILE>.npy.json`サイドカー（`cols`、`rows`、`res_m`、`houdini_center_x/z`、`nodata`）が隣に必要です。

---

## 8. オプション — AMD GPUレンダリング（ProRender）

HoudiniのKarma XPU GPUパスはNVIDIA/OptiX専用です。**AMD Radeon**（RDNA2 / gfx1030以降）では、オプションの`AMDProRender/`アドオンが、Houdini 21 / USD 25向けにネイティブビルドされたAMDの`hdRpr`レンダーデリゲートをインストールし（AMDはH21向けのビルド済みプラグインを提供していません）、Solaris上でGPU Hydraレンダラーとして**「RPR」**が現れます。これは中核のMCPとは独立しています — [AMDProRender/README.md](../AMDProRender/README.md)に従って、ビルド済みリリースをダウンロードするか、ソースからビルドしてください。
