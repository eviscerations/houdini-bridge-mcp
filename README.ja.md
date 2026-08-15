# houdini-bridge-mcp

**AIチャットからSideFX Houdiniを操作 — セキュリティ最優先のデータ専用コントロールサーフェスであり、AIが書くのは*検証済み*ラングルのみで、任意コードは一切書けません。**

AIチャットクライアントから[SideFX Houdini](https://www.sidefx.com)を、その創作領域の広範囲にわたって操作できるWindowsネイティブのMCP（[Model Context Protocol](https://modelcontextprotocol.io)）サーバーです。操作は**任意コード実行の経路を持たない、型付き・検証済みツール**の固定カタログを通じて行われます。AIはノードネットワークを構築・検査し、*検証済みで境界付きの*ラングルを書くことができます。重いクックやレンダリングを実行するのは**ユーザー自身**です。さらに、Houdiniを*学ぶ*ための安全な手段にもなります — すべてのステップがガイド付きで、説明可能かつサンドボックス化された操作であり、ブラックボックスではありません。カタログは広範です。ジオメトリとクリーンアップ・インスタンシング・シミュレーション（FLIP/Pyro/RBD/Vellum）・**キャラクターリギングとアニメーション**（KineFX、Crowd、Muscle）・COP/画像コンポジット・ルックとマテリアル・ML/ONNX・SideFX-Labs（tree/biome/world-building）・レンダリングとエクスポート — そしてこれらに加えて、標高を実スケールで再投影・配置する独自の**実世界ジオデータのレーン**（DEM / USGS 3DEP / LIDAR）を備えます。Houdiniとお使いのAIクライアントと並んで動作する1つのバイナリ、それがインストールのすべてです。

> **ステータス:** **v0.1.0リリース済み** — セキュリティ強化済み、機能完成済み。Houdini内エグゼキューター（型付きツールサーフェス）、地形ダウンローダー（グローバル＋国内カバレッジ）、そしてRust製ドライバーバイナリ＋Houdiniパッケージのすべてが出荷済みです — ゲートウェイは[Releases](../../releases)ページから入手してください。**対象: Houdini 21.0.671**（Apprenticeで動作します。Houdini 22は存在しますが、ここではまだ採用していません）。Windows優先で、他プラットフォームは後日対応します。

---

## Quickstart

**初めての方／コーダーではない方はここから。** 多くのHoudiniユーザーはすでにコードとターミナルの中で生活していますが、あなたはその**必要はありません**。動かすまでの流れは、プログラムを1つ入手し、そのウィンドウでボタンをいくつかクリックし、Houdiniを起動し、AIクライアントに設定の小さなブロックを1つ貼り付ける — それだけです。以下の3ステップが全体像の地図です。さらに下にある番号付きの**ステップ1〜7**が各ステップを詳しく解説します。コマンドラインに触れるのは、プログラムをダウンロードする代わりにソースからビルドすることを選んだ場合だけです。

手元に用意しておくもの: **Houdini 21.0.671**（無料の**Apprentice**エディションで問題ありません）、**Windows** PC、そしてMCPを話せるAIクライアント（Claude Desktop、Cursorなど）。ディスク上の1つのフォルダが、AIが触れることを許されるプロジェクトになります — ステップ3で選びます。

動作するセットアップまでの3ステップ（詳細は以下のステップ1〜7）:

1. **ゲートウェイを入手** （AIとHoudiniをつなぐ唯一のプログラム） — Releasesからビルド済みの`houdini-bridge-mcp.exe`を**ダウンロード**する（コーディング不要）か、ソースから**ビルド**する（`cd gateway && cargo build --release`、Rustツールチェーンが必要）かのどちらかです。ランタイム依存のない単一ファイルです。
2. **インストールとアーム** — ゲートウェイを実行すると、小さなGUIウィンドウが開きます。その中で、**Install Houdini package**をクリックし（Houdiniを自動接続するよう配線します）、**working directory**（作業ディレクトリ）を設定して**Apply**をクリックし（AIが読み書きできる唯一のフォルダ）、**Auto-arm**をオンに切り替えます。そしてHoudiniを起動すると、ステータスピルに**Armed**と表示されるはずです。このマシン以外からアクセスさせる前に、ファイアウォールスクリプトを実行してください（ステップ4）。
3. **AIクライアントを接続** — AIクライアント（Claude Desktop、Cursorなど）に対して、設定に小さなJSONブロックを1つ貼り付けることでゲートウェイの場所を伝え（ステップ6にコピー＆ペースト可能な形で用意しています）、クライアントを完全に再起動し、ステップ7の確認を実行して、AIがHoudiniシーンを認識できることを確認します。

---

## なぜ他と違うのか

他のHoudini/Blender向けMCPサーバーは、モデルに*任意のPython実行*を公開しています — 強力ですが、それは設計上リモートコード実行そのものです（調査した範囲では、同種のブリッジはどれも`execute_code`スタイルのツールを出荷しており、広く使われているあるBlenderブリッジには文書化されたリモートコード実行の問題があります）。本プロジェクトはその逆です。

- **構造的にデータ専用。** AIが呼び出せるのは、**1,467**個の型付き・検証済み操作からなる固定レジストリだけです。任意コードツールも、汎用のノードパラメータ設定ツールも、生のVEX/Pythonの経路も、意図的に**存在しません** — これらはカタログに単に存在しないため、この境界を言葉で突破することはできません。サーバーができることの集合は、列挙されたツールリストそのものです。
- **検証済みの記述 — 抜け道ではなく、差別化要因。** 唯一のコードを運ぶツールである`set_attrib_expr`（オプトイン、**デフォルトで無効**）は、VEXの属性スニペットを受け取り、**Houdiniが目にする前に許可リストと照合して検証します**: ファイル/ホスト/ネットワークへのアクセスなし、許可リストに載った関数のみ、そして証明可能な形で**全域的 — 必ず停止します**。制御フローは、条件分岐、**静的に境界付けされたカウント付きループ**（`for` — リテラルまたは`min()`でクランプされた反復上限）、そして**リーフのみのスナップショット有限な配列ループ**（`foreach` — 反復回数はVEXが入口で確定し、他のループの内側にネストしたり内側に含んだりできません）です。`while`/`do`/`gather`は禁止のままなので、無限ループを構成する手段は存在しません。
  3つの機能が、それぞれ*独自の*独立したデフォルト無効の同意の背後に重なっています。境界付きループ（`allow_attrib_loops`）、**削除系のトポロジー編集**（`removepoint`/`removeprim`、`allow_attrib_geoedit`）、そして**構築／成長**（`addpoint`/`addprim`/`addvertex`/`removevertex`、`allow_attrib_geogrow`） — いずれもinput-0の作業ジオメトリに固定され、各同意は独立しています（1つを有効にしても他が有効になることはありません）。ほとんどのラングル作業はいずれにせよ*型付き*オペレータでカバーされます（フィールド演算、ボクセルごとの計算、`vdb_*`によるCSG/アドベクション）。`vex_reference`はまた、手貼り用のオフライン関数リファレンスも提供します。

  **これは他のどのHoudini MCPも守れていない一線です。AIはリモートシェルをあなたに渡すことなく、本物の実用的なラングルを書けます。** サードパーティ製のブリッジはどれも未検証の`execute_code`/生VEXを出荷しており — 設計上RCEです。SideFX自身が近く提供する公式MCPは、*生成された*コードを事後に正しさの観点で検証するだけで、しかもリギングに限られます。本プロジェクトは、*入力の境界付き部分集合を、実行前に、ツールセット全体にわたって*検証します — 小さなドアではなく、より厳格なモデルです。
- **Houdiniを学ぶ、単に操作するだけでなく — 安全に。** すべてのアクションは型付き・サンドボックス化された*説明可能な*操作であり、AIは提案する検証済みラングルそのものをあなたに手渡します — つまり、ガイド付きの家庭教師にもなります。何かを作るよう頼み、ネットワークをどう配線するかを見て、その*理由*を読む。AIが行うことはどれも、あなたのマシン上で任意コードを実行したり、プロジェクトフォルダ外の作業に触れたりできません。だからこそ、初心者の最初のシーンにとっても、ロックダウンされたパイプラインにとっても同じく安全です。安全性を保つのと同じレールが、Houdiniが実際にどう動くのかを学ぶための、低リスクな場所にしてくれます。
- **1つの作業ディレクトリ。** すべてのファイルの読み書きは、あなたが選んだ単一のプロジェクトフォルダに`realpath`で制限されます。その外にあるものは、シンボリックリンクやジャンクション経由でも一切到達できません。
- **レンダリングはワイヤー接続のみ。** AIはレンダーグラフ（Karma、テクスチャベイク）を構築しますが、それを実行するのは**あなた**です。AIが自らレンダリングを起動することはありません。
- **実世界ジオデータのために作られた。** DEM / 3DEP / LIDARを狙った唯一無二の存在です。標高を実スケールで再投影・配置し、ポイントクラウドをきれいなメッシュに再構築し（有機的なブロブではなく、平面フィットとリメッシュ）、タイルを正しい地球フレームに固定できます。
- **地形だけでなく、広範。** 地理空間パイプラインが専門ですが、同じ型付き・データ専用のサーフェスがHoudiniのほとんどをカバーします。モデリングとクリーンアップ、主要なソルバー、**キャラクターリギングとアニメーション**（KineFXのスケルトン/キャプチャ/デフォーム、Crowd、Muscle）、COP画像コンポジット、ML/ONNX、そしてSideFX-Labsのtree/biome/world-buildingツールセット — すべて同じRCEなしの境界の下にあります。

---

## AIとともにHoudiniを学ぶ

Houdiniはその奥深さで有名で、大半の人がつまずくのは空のネットワークを前にしたあの瞬間です。このブリッジは、腰を据えて実際にHoudiniを*学ぶ*ための、ガイド付きで低リスクな方法です — あなたが望むものを説明すると、AIがライブセッション内でそれを構築し、あなたはネットワークが形になっていく様子を見守ります。

- **おもちゃではありません。** ツールサーフェスは、本物のHoudiniの広範で実用的な領域に届きます — モデリングとクリーンアップ、ジオメトリのシミュレーション設定（FLIP / Pyro / RBD / Vellum）、キャラクターのリグとアニメーション（KineFX、Crowd、Muscle）、COP画像コンポジット、ルックとマテリアル、そしてSideFX-Labsのtree/biome/worldツールセット。そのまがい物ではなく、本物のワークフローを学べます。（正確に何が対象範囲の内と外なのかは、下の率直なカバレッジ数値を参照してください。）

- **型付きエンドポイントが学習の足場になります。** すべての機能は固定された型付き・検証済みの操作なので、AIは*本物のHoudini操作*にしか到達できません — ソフトウェアが実際に行えることの外へさまよったり、存在しないステップを発明したりはできません。ツールリストそのものがHoudiniの構成の仕方を映しており（SOP/COP/DOP/KineFXのファミリー、Labsツールセット）、AIを縛るサーフェスが、同時にアプリケーションの構造をあなたに教えてくれます。

- **見ているのであって、盲目的に走らせているのではない。** すべての操作は、ゲートウェイGUIの監査ログにライブでストリーミングされるので、稼働中のHoudiniセッション内でAIの作業をステップごとに*見る*ことができます — 一度も目にしないヘッドレスなバッチで実行されるのではなく、ネットワークが目の前でノードごとに構築されていきます。そのライブで見守るモードこそが学習上の利点です。（ヘッドレス動作も、それを望むパワーユーザーのために引き続きサポートされています。）

- **ミスは災害ではなく、学びの機会になります。** AIは間違うことがあります — 誤ったノードを選んだり、パラメータを見誤ったりするかもしれません。要点は、AIが決して誤らないことではなく、型付き・サンドボックス化された*検査可能な*サーフェスが、どんなミスも可視化し、簡単に元に戻せて、無害にすることです。AIが行うことはどれも、任意コードを実行したり、プロジェクトフォルダ外のファイルに触れたりしません。だから、まずいステップは、マシンや作業に損害を与えうるものではなく、*なぜそうなるのかを学びながら捕らえて修正する*ものです。
  - **これこそ、既存の`execute_code`ブリッジの上に構築しなかった理由です。** この設計は、モデルが間違うこと、操られること（プロンプトインジェクション）、あるいは誤作動することを前提とし、そしてエージェントに任意コードと目標を与えることが、文書化された高深刻度の失敗モードであること（サンドボックスを脱出し、自律的かつ検知されずに動作し、認証情報/ネットワーク/ファイルに到達するエージェント）を前提としています。だからこそ、モデルにシェルを手渡すBlender/Houdini MCPから発展させるのではなく、本プロジェクトはコードの経路を完全に断ち、データ専用として作り直しました。固定された型付きカタログ*そのもの*が境界です。制限がそのままセキュリティ特性なのです。完全な論拠は[SECURITY.md](SECURITY.md#design-data-only-executor)を参照してください。

**率直なカバレッジ — 対象範囲の内と外。** 生の数で見れば、カタログはHoudiniの非推奨でないノードタイプの意図的な*少数派*に届きます — カタログ内の**1,467**個の型付きツールとして公開されています（1つのノードタイプが複数のツールで到達されることも多く、VOP / SHOP / COP内部 / PDGといったファミリー全体は、抜け落ちではなく設計上除外されています）。しかしこの生の数字は創作上のカバレッジを*過小評価*しています。なぜなら、それは大半の人が実際に使うワークフローに強く重み付けされ、いくつかの領域全体を意図的に外しているからです。

- **十分にカバー（創作のコア）:** COPコンポジット**約84%**、SOPモデリング/ジオメトリ**約49%**、SideFX-Labs**約65%**、KineFXリグ/アニメーション**約53%**。
- **意図的に対象範囲外（バグではなく、スコープの判断）:** USD / Solaris（LOP）**約10%**、PDG / TOP**0%**（バッチ／依存グラフの領域）、レガシーなCop2およびShopコンテキスト、そしてVOP内部（**1.3%** — 設計上の判断: VOPはグラフ内部の構成要素であり、ブリッジが公開するデータサーフェスではありません）。

要するに、生の数で見ればHoudiniのノードサーフェスのおよそ4分の1ですが、大半の人が実際に使う創作ワークフローに重み付けされ、いくつかの領域全体（USD/Solaris、PDG）を意図的に外しています。新規参入者は、ここで何を学べて何を学べないのかを最初から把握できます。

---

## できること

インストールしてアームすれば、AIチャットクライアントで直接、次のように話しかけられます（パスは、設定した1つの作業ディレクトリからの相対パスです）:

- 「北緯46.5°、西経114.0°あたりの地形を10m解像度で作って、その上にカメラを置いて。」
- 「このバウンディングボックスの標高を取得して、実スケールでインポートして。」
- 「`scans/site.ply`を読み込んで、スペックルを取り除いて、メッシュ化して。」
- 「このハイトフィールドを侵食させて、それからガリーと日陰の斜面をマスクして。」
- 「ビューポートが軽いままになるように、パックインスタンシングで地形に岩を散布して。」
- 「夕方遅めのサンライトを用意して、尾根をフレーミングして。」
- 「そのカメラに向けたKarmaレンダリングを配線して — ボタンは私が押すから。」
- 「地形メッシュをUSDとしてプロジェクトフォルダにエクスポートして。」
- 「このメッシュ用のKineFXスケルトンを作って、キャプチャして、バインドをデフォームでテストして。」
- 「地形を横切るパスを歩くエージェントの群衆をセットアップして。」
- 「その盆地にFLIPシムを流し込んで、ワイヤー接続のみでキャッシュして。」
- 「今シーンには何があって、Houdiniはどれくらいメモリを使ってる？」

---

## 仕組み

```
  AI / MCP client  ──stdio──▶  houdini-bridge-mcp  (one binary: config + GUI + gateway)
                                        │  loopback HTTP
                                        ▼
                               a data-only executor running inside your live Houdini session
```

- **バイナリ**は、小さなGUI（表向きの窓口: Houdiniを探し、作業ディレクトリを設定し、セッショントークンを生成し、すべての呼び出しのライブ監査ログを表示する）であると同時に、AIクライアントがstdio経由で話しかけるヘッドレスなMCPゲートウェイでもあります。
- **ゲートウェイ**は型付きの正面玄関です。すべての`tools/call`は、何かが転送される前にカタログと照合して検証されます — 未知のキーは拒否され、数値は範囲にクランプされ、enumはチェックされ、パスは制限されます。
- **エグゼキューター**は、Houdiniセッション内で自動的に自らをアームし、実際のノードに対して要求された操作を実行する、データ専用のPythonパッケージです。

ゲートウェイとエグゼキューターは、1つの**トークン**、**ポート**、**作業ディレクトリ**を共有します。これらはGUIが書き込む小さな設定ファイルから一元的に供給されます — だから手作業のシェルスニペットも、ポート衝突の駆け引きもありません。

---

## 必要条件

1. **Houdini 21.0.671** — Apprenticeで動作します（無料エディション。試すのにライセンス購入は不要です）。
2. **Rustツールチェーン**（stable） — ゲートウェイを自分で**ビルド**する場合のみ必要です。Releasesからビルド済みの`.exe`をダウンロードするなら不要です。[rustup.rs](https://rustup.rs)
3. **Python** — オプションの地形ダウンローダー（DEMのデータ準備ステップ用の`rasterio`）にのみ必要です。最近のCPythonであれば何でも動作します。初回の実行には不要です。
4. **Windows** — Windows優先で、他プラットフォームは後日対応します。

---

## ステップ1 — ゲートウェイを入手

**コーディングは避けたい？** Releasesからビルド済みの`houdini-bridge-mcp.exe`をダウンロードして、そのままステップ2へ進んでください — ビルドが生成するのと同じ単一バイナリです。**代わりにソースからビルドしたい**場合（またはお使いの環境向けのビルド済みバイナリがまだない場合）は、次を実行します:

```
cd gateway
cargo build --release
```

いずれにしても、最終的に得られるのは1つのファイルです — ゲートウェイはGUIであると同時にヘッドレスなMCPサーバーでもあります。どちらのモードで動作するかは、起動時に1つの環境変数`HMCP_GW_HEADLESS`で選択されます — 未設定ならGUIウィンドウが開き、`1`ならヘッドレスなstdioサーバーが動作します。（通常これを手作業で設定することはありません。ファイルをダブルクリックすればGUIが開き、ステップ6の設定ブロックがAIクライアント向けにヘッドレスフラグを設定します。）

---

## ステップ2 — 自動アームのHoudiniパッケージをインストール

これは、HoudiniのGUIが起動したときにエグゼキューターを自動的にアームする、小さなHoudini[パッケージ](https://www.sidefx.com/docs/houdini/ref/plugins.html)を配置します — これによりブリッジは準備完了の状態で立ち上がり、「サーバーを起動する」ステップは不要になります。

**GUI経由（推奨）:** バイナリを起動し、**Settings → Install Houdini package**。

**または手動で、** 2つの静的パッケージファイルをHoudiniのユーザー設定ディレクトリ（デフォルトは`%USERPROFILE%\Documents\houdini21.0`）にコピーします:

```
houdini_package/houdini-bridge-mcp.json            →  <houdini-user-pref-dir>/packages/houdini-bridge-mcp.json
houdini_package/houdini-bridge-mcp/scripts/456.py  →  <houdini-user-pref-dir>/houdini-bridge-mcp/scripts/456.py
```

パッケージファイルはそのまま配布可能です — 絶対パス、ユーザー名、マシン固有の値を含みません。動的なものはすべて、実行時に共有設定ファイルから読み取られます。

---

## ステップ3 — GUIで設定する

`HMCP_GW_HEADLESS`を未設定のままバイナリを起動してウィンドウを表示させ、次を行います:

1. **Settings** — **executor port**（エグゼキューターのポート）と**session token**（セッショントークン）を確認します（デフォルトのままで問題ありません。トークンは2つの半分の間で共有される秘密です）。
2. **Working dir** — あなたの**プロジェクトルート**を入力します。その下のすべてのサブディレクトリに到達できますが、その外には到達できません。**Apply**をクリックします。
3. **Settings**に戻り、**Auto-arm Houdini**をオンにします。

Apply ＋ Auto-armは、GUI、エグゼキューター、そしてヘッドレスゲートウェイのすべてがライブで読み取る共有設定ファイル（`arm.json`、ユーザープロファイル下）を書き込みます。あとから作業ディレクトリを変更するのは**Apply**するだけです — 再起動不要です。

**`arm.json`の場所／検証済みVEXの有効化。** `arm.json`は信頼のルートです — 作業ディレクトリ、セッショントークン、ポート、機能フラグ — 場所は次のとおりです:

```
%USERPROFILE%\.houdini-bridge-mcp\arm.json     (Windows)
~/.houdini-bridge-mcp/arm.json                 (macOS / Linux)
```

唯一のオプトインなコードレーンである`set_attrib_expr`は、**デフォルトで無効**です。有効にするには、**Settings → Safe-VEX (advanced)**を開いて**Enable safe-VEX (`allow_attrib_expr`)**を切り替えます — 即座に反映されます（エグゼキューターは呼び出しごとにフラグを再読み込みします。再起動不要）。そのパネルには、手作業で編集したい場合のために**Open arm.json**と**Open config folder**のボタンもあります。手作業で有効にするには、ファイル内で`"allow_attrib_expr": true`を設定します。これは**オペレーター専用**のスイッチです — 操作を行うエージェントは`arm.json`に決して到達できず（作業ディレクトリが誤ってその上位ディレクトリに設定されていても立ち入り禁止に保たれます）、AIが自身のコードレーンを有効にすることはできません。終わったら、同じ手順でオフに戻してください。

---

## ステップ4 — ファイアウォールを強化する

エグゼキューターは**フェイルクローズド**でアームします — そのループバックポートへのインバウンド接続をブロックするファイアウォールルールがない限り、アームを拒否します。同梱のスクリプトを、昇格したシェルから一度だけ実行してください:

```
scripts/harden-firewall.ps1              # -Mode loopback (default): loopback-only, single machine
scripts/harden-firewall.ps1 -Mode lan    # allow a trusted studio LAN to reach the executor
```

単一の信頼できるマシンには`loopback`（デフォルト）を使用してください。`lan`は信頼できるスタジオネットワーク上でのみ使用してください。

---

## ステップ5 — エグゼキューターをアームする

Houdiniを起動します。インストールされたパッケージが共有設定からエグゼキューターを自動アームし、コンソールに次が表示されます:

```
[houdini-bridge-mcp] executor armed
```

GUIのステータスピルには、接続されたHoudiniのバージョンとともに**Armed**が表示されます — 大半の人にとって、そのピルが必要な確認のすべてです。Pythonシェルのスニペットは不要です。ターミナルから念のため確認したい場合は（オプション、興味のある方向け — 設定したポートとトークンを使用してください）:

```
curl.exe http://127.0.0.1:8765/health -H "X-HMCP-Token: <your-token>"
```

→ `{"ok": true, "service": "houdini-bridge-mcp", ...}`

---

## ステップ6 — MCPクライアントに登録する

クライアント（例: Claude Desktop — `%APPDATA%\Claude\claude_desktop_config.json`のファイルを編集してください。このパスをエクスプローラーのアドレスバーに貼り付けると見つかります）を、**ヘッドレス**モードのゲートウェイバイナリに向けます（ウィンドウなし — AIが直接操作します）。ゲートウェイは作業ディレクトリ、ポート、トークンを共有設定ファイルから読み取るので、envブロックにはヘッドレスフラグだけがあれば十分です。`command`には、ステップ1の`.exe`のフルパスを設定します:

```json
{
  "mcpServers": {
    "houdini-bridge-mcp": {
      "command": "<path-to-repo>\\gateway\\target\\release\\houdini-bridge-mcp.exe",
      "env": {
        "HMCP_GW_HEADLESS": "1"
      }
    }
  }
}
```

> すべてのWindowsパスに**バックスラッシュを2つ**使用してください。

クライアントを完全に終了して再度開いてください。新しいチャットで`houdini-bridge-mcp`のツールが表示されます。

---

## ステップ7 — セットアップを確認する

1. GUIのステータスピルに、お使いのHoudiniバージョンとともに**Armed**と表示されることを確認します。
2. 新しいクライアントチャットで、シーンレポートを求めます:

   > 「`scene_info`を実行して。」

   応答が成功すれば（hipファイル、フレーム、Houdiniバージョン、`/obj`の内容）、クライアント → ゲートウェイ → エグゼキューターのリンクが端から端まで確認できます。
3. 次に、準備済みのDEMタイルを本物のハイトフィールドに変えます:

   > 「`terrain.npy`から`import_heightfield`して、`terrain`という名前を付けて、表示して。」

両方とも返ってくれば、配線は完了です。初回実行の完全なウォークスルーは[docs/SETUP.md](docs/SETUP.md)を、日常的な運用は[docs/GUIDE.md](docs/GUIDE.md)を参照してください。

---
## 利用可能なツール

**約1,467個の型付きオペレーション**があり、以下のファミリーに分類されています（生成された表は正確な現行カタログを示します）。すべてのツールは検証済みハンドラーであり — 自由形式のコード経路は存在しません。**完全なパラメーターリファレンス：[docs/GUIDE.md](docs/GUIDE.md)を参照するか、セッション中に`node_reference`ツールにライブで問い合わせてください。**

<!-- BEGIN TOOLS (generated) -->
<!-- GENERATED by scripts/generate_docs.py from reference/catalog.json — do not hand-edit. -->

### 取得とインポート

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `acquire_terrain` | ある場所の実世界の標高を取得し、作業ディレクトリ内でHoudiniですぐ使えるタイルへと準備します。 | 11 optional |
| `create_geo` | 空の/objジオメトリを作成します。必要に応じて開始プリミティブSOPをシードとして配置できます。 | `name` (+1 optional) |
| `import_pointcloud` | .plyまたは.bgeoのポイントクラウド（LIDAR、フォトグラメトリ、スキャン点群）をFile SOP経由で新しい/objジオメトリに読み込み／インポートします。up_axis z_upはZ-upの測量データをHoudiniのY-upへ回転させ、downsampleはN点ごとに残して重いクラウドを軽量化し、recenterは原点へ移動させます。 | `path`, `name` (+3 optional) |
| `import_heightfield` | 準備済みのDEM（.npy + .jsonサイドカー）をHoudiniのハイトボリュームとしてインポートし、共有プロジェクト原点上の真の標高に配置します（Z反転）。 | `npy`, `name` (+1 optional) |
| `import_ecef_tile` | 準備済みのDEMタイル（(H,W,3)の位置を持つprep_ecefの.npy）を、真の位置と標高で湾曲したクアッドメッシュとしてグローブ上にピン留めします。 | `npy`, `name` (+1 optional) |
| `list_working_dir` | 制限された作業ディレクトリ内のファイルとフォルダーを一覧表示し、インポート前にどのアセットが存在するかを発見できるようにします — 「自分のファイルが見えますか？」への答えです。 | 5 optional |
| `import_geo` | メッシュジオメトリファイル — .obj、.bgeo/.bgeo.sc、.fbx、.stl、.ply、.geo、その他のFile-SOP対応フォーマット — を新しい/objジオメトリに読み込み／インポートします。include_prim_typesはパックドジオメトリとして読み込みます（重いアセット向けのフラットメモリ）。 | `path`, `name` (+1 optional) |
| `import_alembic` | Alembicアーカイブ（.abc） — アニメーション／キャッシュ済みメッシュ、カメラ、トランスフォーム — をAlembic SOP経由で新しい/objジオメトリに読み込み／インポートします。groupnamesはアーカイブパスをどうプリミティブグループにするかを選び、polysoupはポリゴンをメモリ軽量なpolygon-soupプリミティブとして読み込みます。 | `path`, `name` (+2 optional) |
| `trace_raster` | 画像ラスター（.png/.jpg/.tif）をTrace SOP経由で2Dアウトラインカーブへトレース／ベクトル化します — ロゴ、シルエット、マスク、マップを、押し出し／スイープ用のポリゴンカーブに変えます。 | `file`, `name` (+2 optional) |
| `osm_filter` | SideFX Labs OSM Filter — インポートしたOpenStreetMapジオメトリから、必要なフィーチャークラスのみを残します（入力0 = osm_importの出力）。 | `input` (+12 optional) |
| `osm_buildings` | SideFX Labs OSM Buildings — 入力0（`building`プリムアトリビュートを持つosm_import / osm_filterの出力）の閉じたOpenStreetMapフットプリントポリゴンから、3Dの建物マスを押し出します。 | `input` (+8 optional) |
| `obj_importer` | SideFX Labs OBJ Importer — Wavefront .objファイル（`file`、READ制限）と、任意のカスタム.mtl（`custom_mtl`、READ制限）をインポートする、新規の/obj geoです。 | `name`, `file` (+1 optional) |
| `fbx_archive_import` | SideFX Labs FBX Archive Import — FBXファイル（`file`、READ制限）をマージされたHoudiniジオメトリとしてインポートする新規の/obj geoで、任意でマテリアル／アニメーション／ボーンを含みます。 | `name`, `file` (+10 optional) |
| `multi_file` | SideFX Labs Multi File — 最大8個のジオメトリファイル（`file1`..`file8`、各READ制限）を一度にインポートしてマージする新規の/obj geoで、任意で各ファイル名から`name`アトリビュートを付与します。 | `name`, `file1` (+9 optional) |
| `regions_from_image` | SideFX Labs Regions From Image — 画像（`image`、READ制限）を読み込み、色を量子化した領域ジオメトリを生成する新規の/obj geoです（`num_colors`個の領域、`smoothing`が境界を柔らかくします）。 | `name` (+9 optional) |
| `trace_psd_file` | SideFX Labs Trace PSD File — レイヤー付き画像（`file`、READ制限、Photoshopの.psd）を読み込み、そのレイヤーを2Dポリゴンアウトラインへトレースする新規の/obj geoです。 | `name`, `file` |
| `las_import` | ネイティブのLAS/LAZ/E57 LIDAR取り込み（実際の測量／航空測量の納品フォーマット）を新しい/obj geoに行います。 | `name`, `file` (+13 optional) |
| `osm_import` | OpenStreetMapの道路／建物／フットプリント（会場コンテキストのジオメトリ）を新しい/obj geoにインポートします。 | `name`, `file` (+4 optional) |
| `usd_import_sop` | USDファイルを、新規の/obj geo内のSOPジオメトリとしてインポートします（SOPコンテキストの`usdimport` — USDステージからネイティブHoudini SOPへの読み取りブリッジ）。 | `file` (+12 optional) |

### 地形とハイトフィールド

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `heightfield_crop` | ハイトボリュームをメートル単位のサイズボックスへクロップ／リサイズ／再ウィンドウ化します。sizex/sizeyはウィンドウの幅と長さ、center [x,y,z]はウィンドウの位置（cropmode=replaceでより大きなフィールド上をスライドさせられます）、cropmodeはintersect（重なりに合わせて切り取る、デフォルト）、replace（新しいボックスを使い、ボーダーポリシーで元の外へ拡張）またはunion（両者のbbox）、voxelpadはパディングボクセルを追加します。 | `input` (+6 optional) |
| `heightfield_patch` | パッチのハイトボリューム（input1）からフィーチャーを、なめらかな境界でベース（input0）へ転写／ブレンドします — 隣接するDEMタイルをモザイク合成したり、マスクした領域をスタンプしたりします。scaleは転写前にパッチ（グリッド＋フィーチャーの大きさ）を一様にスケールし、heightscaleは転写されるフィーチャー高さのみをスケール、tx/tzは平行移動、ryは転写前にパッチをY軸まわりに回転、centerpatchはこれらのハンドルをマスク領域上でピボットさせます。 | `input`, `patch` (+7 optional) |
| `convert_heightfield` | ハイトボリュームを、レンダリング／エクスポート可能なジオメトリへ変換します。conversionは出力を選び（poly \| polysoup 高密度で非編集 \| vdb 3Dボリューム）、surftypeはポリゴンの接続性（三角形／クアッドが有用な地形レイアウト）、lodはDensity＝出力解像度の比率（0.5＝半分の解像度、2＝4倍のスーパーサンプル）、bake_colorsはハイトフィールドマテリアルをポイントCdとしてメッシュにベイクして、成果物がグラデーションを保持するようにし、extrude_base + depthは押し出したソリッドベースを追加します（プリント／CFD向けに水密）。 | `input` (+8 optional) |
| `heightfield_morph` | 名前付き/objハイトフィールドの高さレイヤーへのグレースケールモルフォロジーで、分離可能なmin/maxボリュームラングルのチェーンとしてサーバー側で構築されます（単一のネイティブSOPはありません）。op: dilate（ピークを成長）\| erode（谷を成長）\| close（周囲の包絡まで谷を埋め、ピークを保持）\| open（細いピークを除去）。radius_mはカーネル半径をメートルで設定します（voxelsizeを介してボクセルへ変換）。 | `name` (+5 optional) |
| `heightfield_fill` | マスクされたラプラシアン緩和で、Jacobiボリュームラングルのチェーンとしてサーバー側で構築されます（単一のネイティブSOPはありません）：マスクされたボクセル（mask==1）を近傍の平均で埋めつつ、マスクされていないボクセル（mask==0）をディリクレ境界として保持します — チャネル／穴をまたいでなめらかな面を再構築します。iterations＝Jacobiのステップ数（多いほどなめらか／遠くまで充填）、seed_layerは任意でマスクされたボクセルを事前シードします。 | `name` (+5 optional) |
| `heightfield_tilesplit` | ハイトフィールドをtiles_x × tiles_yのグリッドへ分割します（ネイティブのLOD／ストリーミング／タイルごとのゲームエンジンエクスポート）。 | `input` (+7 optional) |
| `heightfield_clip` | 高さ値をmin/maxの帯へクリップします（外れ値のクランプ／メサ状の平坦化）。minheight/maxheightはクリップの下限／上限（それぞれが自身のクリップトグルを自動で有効化）、soft_clipはハードなクランプの代わりにクリップ値への遷移を柔らかくし（デフォルトで有効）、clip_strengthはその鋭さを設定します。 | `input` (+5 optional) |
| `heightfield_cutout` | ジオメトリ（input1）で境界づけられた非矩形のハイトフィールド領域を切り抜き、`Alpha`表示レイヤーに書き込みます（Alpha=0.5でカットアウト）。 | `input` (+5 optional) |
| `heightfield_erode` | 選んだフィーチャースケールでの水成＋熱による侵食（HeightField Erode 3.0）。 | `input` (+27 optional) |
| `heightfield_visualize` | ハイトフィールドにカラーランプを適用し、その標高（および任意のマスクの色付け）をビューポートで見えるようにします — ネイティブのボクセル空間に挿入します。layerは3D面として表示される高さレイヤー（ノードパラメーター`heightvolume`）、color_layerはその上にマスクレイヤーを色付けし、presetは組み込みのディフューズスキーム（infrared/pink/mono/blackbody/bipartite）を選び、min_elevation/max_elevationは高さ→ランプの範囲を固定します。あるいはcompute_rangeを有効のまま（デフォルト）にして、SOPのCompute Rangeボタンを自動的に押させ、ランプが実際の標高にマッピングされるようにします。 | `input` (+8 optional) |
| `heightfield_maskbyfeature` | 1つ以上のフィーチャー（傾斜／高さ／向き／曲率）で地形をマスクします — ピーク、谷、雪線、植生可能な地面を切り出します。 | `input` (+17 optional) |
| `heightfield_maskbyocclusion` | アンビエントオクルージョンのマスク（窪み／裂け目／遮蔽された地面）をマスクレイヤーへ書き込みます — オクルージョンとは、各ボクセルの周囲の球のうちどれだけが近くの地形で遮られているか（レイキャスト）です。minexposure/maxexposureはオクルージョンの帯をマスクへ再マッピングし（min未満→0、max超→1）、dohemisphereは上方（空）の半球のみをサンプリング、viewdistanceはレイの長さ（0＝無限、長いほど正確／低速）です。 | `input` (+9 optional) |
| `heightfield_maskbyshadow` | 与えられた太陽方向から影になる領域をマスクします（雪解け、コケ、日向／日陰のドレッシングを駆動）。lightdirは太陽の方位角（度、0＝+X方向、+90＝-Z方向に光）、lightangleは太陽の仰角（度、低いほど影が長い）、opacityは影内のマスク値、falloffは影の境界をぼかします（0＝ハード）。 | `input` (+9 optional) |
| `heightfield_maskbyobject` | 他のジオメトリ（input1、object-merge済み）からハイトフィールド領域をマスクレイヤーへマスクします — サーフェスジオメトリの2Dアウトライン、またはフォグ／SDFボリュームの交差です（3D高さ投影にはheightfield_projectを使ってください）。method: ray（サーフェスを下方へ投影）\| volume（フォグ）\| sdf、maskdir（rayメソッド）：両側から投影 \| 上 \| 下、maxdistはミスとなるまでの最大レイ距離、valueはジオメトリがヒットした箇所のマスク値、blurradiusはマスクを柔らかくします。 | `input` (+11 optional) |
| `heightfield_flatten` | ハイトフィールドのマスクされた領域を平坦化します（フィーチャーを消す、または建物のフットプリントをならす）。method: value＝マスク領域を`elevation`に設定（elevationを設定するとこのモードを強制）、average＝マスク領域自身の平均へならす、slope＝境界をなめらかに補間（デフォルト、elevationは無視）。mask_layerが平坦化をゲートし（0＝手つかず、1＝完全に平坦）、blurradiusはマスクの端を柔らかくします。 | `input` (+5 optional) |
| `heightfield_maskbyconcavity` | 凹んだ領域（河床／谷／溝）をマスクレイヤーへマスクします — 凹度は空の可視性（各ボクセルから飛ばすレイ）で測られます。concavity/maxconcavityはマスクの帯を設定し（凹度がconcavity以上maxconcavity以下のボクセルを追加）、invertはその帯の外側をマスク、combineは既存のマスクとマージ、viewdistanceはレイの長さ（長いほど正確／低速）です。 | `input` (+7 optional) |
| `heightfield_deform` | 変化するハイトフィールドによってジオメトリを変形させます：点は、レスト地形と現在の地形との差だけ上下し（任意で新しい傾斜へ回転）します — 例：水面上でパックドプロップを浮かせたり、アイソスタティックリバウンドの傾きを適用したりします。 | `input` (+3 optional) |
| `heightfield_layer` | 名前付きハイトフィールドレイヤーへのレイヤーごとのユーティリティ。op=clearはレイヤーのすべてのボクセルを`value`に設定します。op=propはレイヤーのボーダー拡張ポリシー`border`（constant \| repeat \| streak \| sdf）を設定します — フィールドをタイル化／マージする際に重要です。op=isolateはレイヤーを`mask`へコピーし（任意でoverwrite_height/overwrite_maskを介して`height`へも）、デフォルトの赤色付けビューポートでそれを表示します。 | `input` (+7 optional) |
| `terrain_analysis` | Labs Terrain Analysis：スキャッタリング、経路探索、シェーディング向けに、傾斜／曲率のポイントアトリビュートを書き込みます。 | `input` (+7 optional) |
| `add_tile_packed` | ベイク済みの.bgeo(.sc)タイルをパックドディスクプリミティブ（遅延ロード、表示コストほぼゼロ）として新しい/obj geoに読み込みます — 多数の地形タイルをストリーミングするメモリ安全な方法です。 | `name`, `path` (+3 optional) |
| `set_tile_lod` | ヒーローのスワップのために、1つのパックドタイルのビューポートLOD（ボックスプロキシ⇔フルジオメトリ）を切り替えます — 名前付き/obj geo下でadd_tile_packedが作成した`packed_tile` File SOPを対象とします。 | `name` (+1 optional) |
| `heightfield_noise` | ハイトフィールドレイヤーにプロシージャルノイズを追加します（フルノイズサーフェス：合成、amp/scale/offset、basis+fractal、オクターブ、gain/bias、クリッピング、lattice/gradientワープ）。 | `input` (+32 optional) |
| `heightfield_blur` | ハイトフィールドレイヤーをブラー／ボックスブラー／拡張／収縮／シャープ化します。 | `input` (+10 optional) |
| `heightfield_flowfield` | ハイトフィールドに雨を降らせ、水を下り坂へ流して、フロー／フロー方向レイヤーを計算します（侵食マスク、堆積、簡易な地形の谷を駆動）。 | `input` (+15 optional) |
| `heightfield_project` | 入力ジオメトリ（オブジェクト、input1へobject-merge）をハイトフィールドレイヤーへ3D高さとしてレイキャストします — 実ジオメトリを地形にスタンプします（平坦な2Dアウトラインマスクにはheightfield_maskbyobjectを使ってください）。 | `input` (+16 optional) |
| `heightfield_scatter` | ハイトフィールドのマスクレイヤーを使って、タグ付きの点を全体に散布します（アセット／インスタンスの配置、heightfield_scatter 2.0）。 | `input` (+45 optional) |
| `heightfield_terrace` | ハイトフィールドに段状のテラス／メサを刻みます（heightfield_terrace 2.0）。うねりノイズとメサ／崖の傾斜マスクを備えます。 | `input` (+22 optional) |
| `heightfield_remap` | ハイトフィールドレイヤーの値範囲を再マッピングします（heightfield_remap） — 高さ／マスク／任意のスカラーレイヤーを[input_min,input_max]から[output_min,output_max]へ再スケールします：DEMを0..1に正規化、マスクのコントラストを強調、レイヤーの反転（出力のmin/maxを入れ替え）、標高の圧縮などです。 | `input` (+9 optional) |
| `heightfield_resample` | ハイトフィールドを新しい解像度へリサンプルします（heightfield_resample） — 巨大なDEMを高速なイテレーション用にダウンレゾするか、侵食／エクスポート前にアップレゾします。resolution_scaleは現在の解像度に乗算し（0.5＝半分、2＝2倍）、あるいはexact_resolution + division_modeで正確なターゲットを指定します。 | `input` (+7 optional) |
| `hf_combine_masks` | SideFX Labs Combine Masks — 入力されたハイトフィールド（`input`、入力0）上のハイトフィールドマスクレイヤーをマージし、後処理します。 | `input` (+11 optional) |
| `hf_insert_mask` | SideFX Labs Insert Mask — 2つ目のハイトフィールド（`mask`、入力1）から名前付きのマスク／高さレイヤーを、ベースのハイトフィールド（`input`、入力0）へコピーします。 | `input`, `mask` (+4 optional) |
| `terrain_segment` | SideFX Labs Terrain Segment — 入力されたハイトフィールド（`input`、入力0）を、tiles_x × tiles_yのグリッドのメッシュ化された地形タイルへ分割します（そのクックされたSOP出力そのものが分割されたジオメトリです）。doextrude+depthはソリッドなスカートを付け、flatは平坦なメッシュへベイクし、iterationsは適応密度のリメッシュを駆動します。 | `input` (+12 optional) |
| `terrain_texture` | SideFX Labs Terrain Texture — ワイヤー接続のみの地形マップベイカー：入力された地形（`input`、入力0）のノーマル／ハイト／オクルージョン／キャビティ／曲率マップを`outputdir`へベイクします。 | `input` (+15 optional) |
| `terrain_layer_export` | SideFX Labs Terrain Layer Export — ワイヤー接続のみのエクスポーターSOPで、入力されたハイトフィールド（`input`、入力0）をUnreal/Unityのランドスケープ用ハイトマップ＋ペイントレイヤー画像として`output`へ書き出します。 | `input` (+12 optional) |
| `terrain_layer_import` | SideFX Labs Terrain Layer Import — Unreal/Unityのランドスケープ用ハイトマップ画像（`sHeightmap`）を新規の/objハイトフィールドへ読み込むソースノード（入力0個）です。voxelsizeは結果のHF解像度を設定し、bFlopは行の順序を反転します。 | `name` (+3 optional) |
| `biome_define` | SideFX Labs Biome Define — 1つのバイオームの気候プロファイル（名前＋平均気温／降水量＋土壌フラグ）を設定ポイントストリームとして定義します。 | 9 optional |
| `biome_plant_define` | SideFX Labs Biome Plant Define — 1つの植物種とその気候耐性（下限／推奨／上限の気温＆降水量）、生活型（Tree/Shrub）、バウンズ／幹の半径、スケール、最大密度を定義します — biome_scatterが植生を配置するために読み取るレコードです。 | 27 optional |
| `biome_definitions_file` | SideFX Labs Biome Definitions File — バイオームライブラリをJSONへ／から直列化します。 | 6 optional |
| `biome_plant_definitions_file` | SideFX Labs Biome Plant Definitions File — 植物種ライブラリをJSONへ／から直列化します（plant_define向けのbiome_definitions_fileのミラー）。 | 6 optional |
| `biome_profile` | SideFX Labs Biome Profile — バイオームごとの平均気温＆降水量を持つ、統合されたバイオームプロファイル（biome_initialize / region_assign / curveノードが消費するbiomeprofile.json）を保持／書き込みます。 | `name` (+4 optional) |
| `biome_initialize` | SideFX Labs Biome Initialize — パイプラインの入口：地形とバイオーム領域ソースを受け取り、準備済みのTerrain（出力0）＋Biome Regions（出力1）を出力します。 | 28 optional |
| `biome_region_assign` | SideFX Labs Biome Region Assign — 入力された領域ソース（`input`、入力0）のバイオーム領域をバイオームライブラリに対して割り当て、Biome Regions（出力0）＋Guide Geometry（出力1）を出力します。 | `input` (+25 optional) |
| `biome_attributes_evolve` | SideFX Labs Biome Attributes Evolve — 気候アトリビュートレイヤー（気温／降水量／土壌）を、入力された地形（`input`、入力0）全体にわたって物理法則から進化させます：気温は標高とともに低下し（`lapserate`）、降水量は山の風下側で除去され（雨陰：removebydir + rain_x/rain_z方向 + anglespread）、土壌は崖（removebyslope + min/max slope）とプロシージャルノイズ（removebynoise + noise basis/fractal/amp/elementsize）で間引かれます。 | `input` (+34 optional) |
| `biome_attributes_to_terrain` | SideFX Labs Biome Attributes To Terrain — バイオームの気候アトリビュートを、入力された地形（`input`、入力0）へ名前付きハイトフィールドレイヤー（気温／降水量／土壌／バイオームカラー）としてベイクし、下流のシェーディングやエクスポートに備えます。 | `input` (+12 optional) |
| `biome_curve_setup` | SideFX Labs Biome Curve Setup — 作成された領域カーブ（`input`、入力0 — 手描きの境界）に、それが属するバイオーム（`biomename_curve`）とソート順（`biomehierarchy`）をタグ付けし、biome_region_assignがカーブモードで読み取るマージ済みカーブストリームを生成します。 | 5 optional |
| `biome_curve_label` | SideFX Labs Biome Curve Label — 領域カーブ（`input`、入力0）に、プロファイルから取得する代わりに、明示的な気候値（気温／降水量／土壌／バイオームカラー／ソート順）を直接ラベル付けします — biome_curve_setupの手動版です。 | 11 optional |
| `region_assignment_subutil` | SideFX Labs Region Assignment（サブユーティリティ） — バイオーム領域パイプライン内部で使われる内部配管ヘルパー：入力ジオメトリ（`input`、入力0）に対して`lpcount`回ループし、反復ごとに名前付きHDAパラメーター（`hda_parm`）を読み取り、その値を`index_parm`でインデックスされたポイント／プリムアトリビュート（`attrib_name`）へ書き込みます。 | `input` (+5 optional) |
| `convert_regions_to_curves_subutil` | SideFX Labs Convert Regions To Curves（サブユーティリティ） — 入力ジオメトリ（`input`、入力0）上の領域ポリゴンを、領域ごとに1つの閉じたカーブとして、境界カーブプリミティブへ変換します。 | `input` (+2 optional) |

### モデリングとジオメトリ

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `remesh` | 均一三角形化リメッシュ（Remesh 2.0） — 三角形化された／スキャンした面を、スムージング、シミュレーション、クリーンな変形のために、形の整った均一なサイズの三角形へ再構築します。targetsizeはワールド単位のターゲットエッジ長（小さいほど密なメッシュ、高ポリゴン数）、sizing=uniformはどこでも一様なサイズ、sizing=adaptiveは曲率に応じて小さな三角形を集中させます（density＝適応ターゲット密度の乗数）。gradationはuniform⇔adaptiveのブレンドをバイアスします（0でuniform..1で完全に曲率適応）。iterations＝スムージング／最適化のパス数、smoothing＝パスごとの点の緩和強度。min_edge/max_edgeは生成されるエッジ長をクランプします。 | `input` (+13 optional) |
| `polyreduce` | デシメート（PolyReduce 2.0） — シルエットとフィーチャーを保ちつつ、LOD／リアルタイム納品のためにメッシュをポリゴン数の一部へ削減します。targetは削減の対象を選び：poly_percent / pt_percent（パーセンテージ、デフォルト、percentage経由）または poly_count / pt_count（絶対的なfinalcount — LODの主力）。qualitytoleranceは品質を速度と引き換えにします。 | `input` (+11 optional) |
| `boolean` | AをBに対してブーリアン（メッシュCSG）します（boolean::2.0） — ソリッドを切断／結合します。 | `input` (+7 optional) |
| `sweep` | 断面をバックボーンカーブに沿ってスイープしてサーフェスを作ります — カーブ→ジオメトリの要：パイプ、ケーブル、ロープ、レール、道路／川のリボン、建築トリム。shape=tube\|square\|ribbonは組み込みプロファイルを使い（tube: radius、square/ribbon: width、colsが密度を設定）、shape=inputは自分のcross_section SOP（入力1）をスイープします。 | `input` (+15 optional) |
| `polyextrude` | ポリゴン面を法線に沿って外側へ押し出します（polyextrude::2.0） — フットプリントからの建物、グリーブル、厚み付けの主力。distance＝押し出す深さ、insetは押し出したキャップを内側へ縮め、divisionsは側壁ループを追加、twistはキャップを回転させます（度）。 | `input` (+19 optional) |
| `polybevel` | エッジや点をベベル／丸めます（polybevel::3.0） — ハードサーフェスのエッジ軟化オペ（面取り、フィレット、溶接シーム）。offset＝フィレットサイズ、divisions＝丸めのセグメント数（1＝平坦な面取り、多いほどなめらかな丸め）、shapeはプロファイルを選びます（round \| chamfer \| crease \| solid）。 | `input` (+8 optional) |
| `deform` | opで選ぶ単一ノードのデフォーマー：bend（ジオメトリを軸に沿って曲げる、`amount`＝角度°）、twist（`amount`＝ねじり強度°）、mountain（フラクタルノイズで法線に沿って変位、`amount`＝高さ、`frequency`＝ノイズのエレメントサイズ）、attribnoise（ノイズをアトリビュートへ、`amount`＝振幅、`frequency`＝エレメントサイズ）、lattice（ケージワープ、divsx/divsy/divszを設定）、peak（点を法線に沿って押す、`amount`＝距離）。 | `input` (+7 optional) |
| `drape` | 入力の点をコリジョンサーフェス上へ投影／ドレープします — 散布したプロップ、カーブ、グリッドを地形の上に落ち着かせます。 | `input` (+5 optional) |
| `transform` | シーン内の3Dジオメトリを移動／回転／スケールします（Transform SOP） — オブジェクトやポイント／プリムグループを3D空間に配置します。translate、rotate（度）、uniform＋軸ごとのscale、pivot、グループ制限、transform/rotateの順序。 | `input` (+15 optional) |
| `select_group` | 境界による選択の後に逆側を削除します。bboxは内側のジオメトリを保持し、そうでなければpatternが名前付きグループを選択します。 | `input` (+4 optional) |
| `merge` | 複数のSOPを1つのストリームへマージします。 | `inputs` (+1 optional) |
| `switch` | 整数インデックスで選択して、複数の入力のうち1つを出力します — バリアント／LODの組み立てとA/Bの切り替え。 | `inputs` (+2 optional) |
| `null` | 無操作のパススルー／名前付きウェイポイント — ランドマークの慣習：意味のある結果ごとにnullを配置し、OUT_<name>（安定した結果ハンドル。下流のobject_merge/参照は名前を対象とするため、上流にノードを挿入しても壊れません）、IN_<name>（外部ジオメトリの入口）、またはCONTROL（ドライバーパラメーター／スペア入力）と名付けます。 | `input` (+1 optional) |
| `sort` | 点および／またはプリムを決定論的に並べ替えます — コピースタンプ／インスタンシングの決定性のための安定したID。 | `input` (+7 optional) |
| `polysplit_loop` | パラメトリックなエッジループを挿入します（polysplit::2.0 Edge-Loopモード） — クアッドを保ちつつ補助／コントロールループを追加します。 | `input`, `seed_edge` (+3 optional) |
| `poly_split` | 面をまたぐフリーフォームのエッジパスをカットします（polysplit::2.0 Shortest-Distanceモード） — n-gon／ブーリアンシームを「乗り越えて」新しいエッジ列を通し、クアッドを回復する、機械的リトポの基本オペです。 | `input`, `path` (+6 optional) |
| `copy_transform` | コピー＆トランスフォーム（copyxform）：入力のN個のコピーを、それぞれ累積的な増分トランスフォームで作ります（コピーiにはi倍のtranslate/rotate/scaleが適用されます）。 | `input` (+14 optional) |
| `helix` | ヘリックス／コイルカーブ（spiral SOP）を持つ新規の/obj geoを作成します — スプリング／コイル／ねじの生成器（エジェクターロッドのスプリング、ボルトのねじ山、DNA鎖、螺旋ガイド）。turns＝回転数、height＝軸方向の上昇（0＝平坦な螺旋）、start/end_radiusはコイルをテーパーさせます。 | `name` (+8 optional) |
| `polywire` | カーブ／ワイヤーをソリッドなチューブジオメトリへ面貼りします（polywire） — スプリング、ケーブル、パイプ、ロープ、ワイヤーフレームレンダー、ニューロン、枝。divisions＝断面の辺数（最小3）、segments＝スパンに沿った分割、joint_correctはワイヤーが交わる箇所での座屈を防ぎます。 | `input` (+9 optional) |
| `convex_decompose` | 近似的な凸分解（convexdecomposition） — 凹メッシュを凸包の集まりへ分解します。安価なRBD／物理コリジョンプロキシを作る標準的な方法です（凸包は凹メッシュよりコリジョンがはるかに安価で、ほとんどのソルバーは凸コライダーを好みます）。max_concavity（0..1）はフィットと数のトレードオフ：低いほどタイト＋ハル数が多く、高いほど少数／緩くなります。output=hulls（凸ピース、デフォルト）\| segments（元の面を分割＋タグ付け）。per_pieceは各`piece_attrib`のアイランド（例：`name`）を独立して分解します — フラクチャー後の定番です。 | `input` (+10 optional) |
| `set_color` | 一定の色を割り当てます。 | `input` (+3 optional) |
| `uv` | modeによるUV：project（uvproject）、unwrap（uvunwrap自動）、layout（uvlayout::3.0のアトラスパッキング）、transform（uvtransform）、またはflatten（uvflatten::3.0のシーム駆動）。 | `input` (+17 optional) |
| `uv_transfer` | ソースメッシュから入力ジオメトリへUVセットを転写します — トポロジー変更（remesh/quad_remesh/polyreduce）で破壊されたUVを復元します。 | `input`, `source` (+5 optional) |
| `create_primitive` | プリミティブSOP（box/grid/sphere/tube/line/circle/platonic/torus）を持つ新規の/obj geoを作成します — ハードサーフェス＋オーガニックモデリングの出発ブロックです。 | `name` (+10 optional) |
| `skin` | 順序付けられたプロファイルカーブをまたいでサーフェスをロフト／スキンします — 入力は複数のプロファイルプリミティブを持つSOPです（まず並列カーブをマージしてください）。skinはそれらをプリム順にロフトします。output_polygons=falseはスプラインメッシュを生成し、v_wrap=wvはロフトをループへ閉じます。 | `input` (+10 optional) |
| `revolve` | プロファイルカーブを軸まわりに旋回させます → 回転面（花瓶、チューブ、ボトル、ホイール、ランプシェード）。axis+originは旋回軸を定義（デフォルトは原点を通るY）、divisions＝辺数、revolve_type=openarc\|closedarc + angle=[start,end]で部分的なアークを作り、capsは端を閉じます。 | `input` (+11 optional) |
| `mirror` | ジオメトリを平面で反射し、（デフォルトで）シームを溶接します。axis=x\|y\|zは平面法線のショートカット（またはdirx/diry/dirz + originx/originy/originzを与える）、distは平面をオフセットします。keep_original=falseは反射のみに置き換え、weldはシームを融合、operation=clipは反射の代わりに平面で切断します。 | `input` (+15 optional) |
| `dissolve` | エッジ（または点）グループを溶解し、隣接する面をマージします — トポロジーの簡略化です（穴を残して削除するblastとは異なります）。 | `input`, `group` (+6 optional) |
| `bridge` | 2つのエッジループを接続するチューブ／スカートへブリッジします（polybridge）。 | `input`, `src_group`, `dst_group` (+12 optional) |
| `pointdeform` | ケージの動きで入力をラップ変形します：rest_cage（input1）→ deformed_cage（input2）。 | `input`, `rest_cage`, `deformed_cage` (+7 optional) |
| `crease` | 下流のsubdivideがそれらのエッジをシャープに保つよう、エッジグループにcreaseweightを書き込みます — 説得力のあるサブディビジョンサーフェスによるハードサーフェスモデリングの鍵です。group＝エッジグループ、weight＝クリース値（0..10）、op＝addto\|set\|delete。 | `input` (+5 optional) |
| `divide` | ポリゴンを分割／三角形化します。triangulate（凸、デフォルトで有効）はmax_sidesを伴い、smooth（Catmull式サブディバイド）はdivisionsを伴い、brick=true + brick_size=[x,y,z]はメッシュをタイル化し、compute_dualは双対メッシュを構築し、remove_shared_edgesはマージします。 | `input` (+10 optional) |
| `polyexpand2d` | 2Dカーブを可変幅のアウトライン／リボンへオフセットします — OSMカーブからの道路、パネルライン、インセット。input＝2DカーブSOP。offset＝半幅、output=curves\|surfaces、inside/outsideはどちらの側を出力するかを選び、width_attribは可変幅のためのポイントごとのアトリビュートを指定します。 | `input` (+10 optional) |
| `lsystem` | L-system（プロシージャルな分岐カーブまたはスイープチューブ — 木、サンゴ、稲妻、成長）を持つ新規の/obj geoを作成します。premise＝公理、rules＝'A=...'という生成文字列のリスト（不活性なタートルグラマーであり、コードではありません）、generations/angle/step/thicknessは型付きスカラー、output=skel\|tube。 | `name` (+10 optional) |
| `create_curve` | 呼び出し側が指定した点から構築したカーブを持つ新規の/obj geoを作成します。 | `name`, `points` (+3 optional) |
| `tree_trunk_generator` | SideFX Labs Tree Trunk Generator — モジュラーツリーチェーンのルート。 | `name` (+24 optional) |
| `tree_controller` | SideFX Labs Tree Controller — ツリー全体の設定（重力／曲げ／光走性、シームブーリアン、LOD）を保持するソースノード（入力0個、出力1個）。 | `name` (+18 optional) |
| `tree_branch_generator` | SideFX Labs Tree Branch Generator — 主力：親から1階層の側枝を成長させます。 | `input` (+30 optional) |
| `tree_simple_leaf` | SideFX Labs Tree Simple Leaf — 1枚の葉（または針葉）のテンプレートカードを持つ新規の/obj geoを構築します。その出力をtree_leaf_generatorの`leaf`入力へ配線して、ツリー全体に散布します。bend=0で平坦な針葉になります。 | `name` (+11 optional) |
| `tree_leaf_generator` | SideFX Labs Tree Leaf Generator — チェーンの終端：葉テンプレートを枝の上に散布します。 | `input` (+21 optional) |
| `quick_basic_tree` | SideFX Labs Quick Basic Tree — `input`（ベースサーフェス／ポイントセット）から育てる1コールの便利ツリーで、モジュラーチェーンを補完します。 | `input` (+15 optional) |
| `maps_baker` | SideFX Labs Maps Baker — ワイヤー接続のみのLODアトラステクスチャベイク。 | `input` (+28 optional) |
| `capsule` | SideFX Labs Capsule — カプセルプリミティブ（円柱の胴体と2つの半球キャップ）を持つ新規の/obj geoです。radius/heightがサイズを、sidesが放射方向の解像度を、bodysegments/capsegmentsが長さ方向の解像度を、directionが長軸を設定します。 | `name` (+6 optional) |
| `cylinder_generator` | SideFX Labs Cylinder Generator — ネイティブのtubeより制御の効くプロシージャルな円柱／円錐／チューブを持つ新規の/obj geoです。uniformradiusは上面＋底面をradiusに結び付け、無効にするとtopradius/baseradiusでテーパーできます。sides/divisionsが解像度を設定し、opencylinder + arcstart/arcendは開いたアークを切り、endcaps + fillmodeは端をキャップします。 | `name` (+14 optional) |
| `disc_generator` | SideFX Labs Disc Generator — 平らなディスク／リング／円環を持つ新規の/obj geoです。innerradius>0でリング／ワッシャーになり、outerradiusがリム。sides/divisionsが解像度を設定し、arcstart/arcendはパイのくさびを切り、orientationは平面を選び、innerheight/outerheightは浅い円錐／漏斗へロフトします。 | `name` (+10 optional) |
| `hexagon_grid` | SideFX Labs Hexagon Grid — 六角タイルのグリッドを持つ新規の/obj geoです。type=polygonは六角面（メッシュ）を構築し、type=pointsは六角の中心のみを出力します。gridshapeはフットプリント（hexagon/triangle/rectangle/parallelogram）、gridsizeはその範囲、cellradiusは六角ごとのサイズ、cellorientationはポインティvsフラットトップ、orientationは平面を設定します。connectivity=connectedは共有エッジを融合します。 | `name` (+7 optional) |
| `quad_sphere_generator` | SideFX Labs Quad Sphere Generator — クアッドのみ（細分化された立方体）の球で、極でピンチしないネイティブ球とは異なりクリーンで均一なトポロジーを持つ新規の/obj geoです。subdivisionsはポリゴン数に対して指数的で（6*4^nクアッド）、7以下にハードクランプされます。 | `name` (+3 optional) |
| `simple_shapes` | SideFX Labs Simple Shapes — `shape`で選ぶ2Dプロファイル形状ファミリー（triangle/diamond/rectangle/trapezoid/polygon/star/double_star/square_star）の1つを持つ新規の/obj geoです。base/heightは矩形系のサイズ、radius/sides/points/innerradiusは多角形＆スター系を駆動します。closedはプロファイルを面に閉じ、adduvsはUVを追加します。 | `name` (+11 optional) |
| `superformula_shapes` | SideFX Labs Superformula Shapes — `shapeselect`で選ぶsuperformulaファミリー（square/circle/triangle/polygon/diamond/star/squircle/rounded_polygon/clover/flower/sunburst/eye/teardrop/heart/custom）の2D形状を持つ新規の/obj geoです。width/heightがサイズ、circpointnumは円／曲線の解像度を設定し、polysides/starspokes+starpinchbloat/flowerspokesは多角形／スター／フラワー系を駆動します。fillshapeはプロファイルをサーフェスへ充填し（そうでなければアウトラインカーブ）、roundcornersは角をベベルします。 | `name` (+10 optional) |
| `quadrangulate` | SideFX Labs Quadrangulate（labs::quadrangulate::2.0） — 三角形化されたメッシュを、三角形ペアをマージしてクアッドへ変換します（トポロジー保存。quad_remeshのような完全な再構築ではありません）。 | `input` (+8 optional) |
| `voxelmesh` | SideFX Labs VoxelMesh（labs::voxelmesh::2.0） — `input`（入力0）を、最長軸に`resolution`ボクセル分だけラスタライズしてVDBにし、その面をメッシュ化することで水密メッシュへ再構築します（ボリュームベースのリメッシュで、ネイティブのサーフェスリメッシュとは異なります）。 | `input` (+11 optional) |
| `connect_polygon_neighbours` | SideFX Labs Connect Polygon Neighbours（labs::connect_polygon_neighbours::1.0） — `input`（入力0）の各ポリゴン重心に点を発生させ、（デフォルトモードでは）面隣接の近傍を結ぶポリラインエッジを作ります — メッシュの双対／隣接グラフです。 | `input` (+6 optional) |
| `edge_group_to_polylines` | SideFX Labs Edge Group to Polylines（labs::edge_group_to_polylines::1.0） — `input`（入力0）から`edgegroup`で指定されたエッジを、個別のポリラインプリミティブとして抽出します。 | `input` (+2 optional) |
| `edgegroup_to_curve` | SideFX Labs Edge Group to Curve（labs::edgegroup_to_curve::1.1） — edge_group_to_polylinesと同様ですが、`group`で指定されたエッジを、接続され順序付けられたカーブへ縫合します（共有端点を連鎖させます）。 | `input` (+8 optional) |
| `symmetrize` | SideFX Labs Symmetrize（labs::symmetrize） — `input`（入力0）を`origin`＋`direction`（法線）で定義される平面で反射し、両半分を対称メッシュへ溶接します。 | `input` (+9 optional) |
| `thicken` | SideFX Labs Thicken（labs::thicken::1.1） — 面／開いたシェルに、法線に沿って`depth`だけ押し出し、壁をブリッジすることで厚みを与えます（ソリッド化）。 | `input` (+10 optional) |
| `boolean_curve` | SideFX Labs Boolean Curve — 2つのカーブ入力の2D／カーブブーリアン。 | `input` (+5 optional) |
| `curve_branches` | SideFX Labs Curve Branches — 入力カーブ（入力0）に沿って子枝のカーブを散布します。 | `input` (+14 optional) |
| `curve_resample_by_density` | SideFX Labs Curve Resample by Density — 入力カーブ（入力0）を非一様な点密度でリサンプルします。 | `input` (+5 optional) |
| `curve_sweep` | SideFX Labs Curve Sweep — バックボーンカーブ（入力0）に沿って断面をスイープし、チューブ／リボンを構築します。 | `input` (+6 optional) |
| `merge_splines` | SideFX Labs Merge Splines — 重なり合うスプラインカーブを、接続されたネットワークへ融合／マージします。 | `input` (+5 optional) |
| `polywire_uv` | SideFX Labs PolyWire UV — エッジネットワークまたはカーブ（入力0）のまわりに、UV付きのpolywireチューブを構築します。 | `input` (+11 optional) |
| `progressive_resample` | SideFX Labs Progressive Resample — 入力カーブ（入力0）を、ポイントごとの`pscale`アトリビュートで駆動される漸進的なセグメント長で均一にリサンプルします。 | `input` (+5 optional) |
| `spiral` | SideFX Labs Spiral — ソースノード（入力0個）：スパイラル／ヘリックスカーブを持つ新規の/obj geoを構築します。 | `name` (+7 optional) |
| `sweep_geometry` | SideFX Labs Sweep Geometry — 断面メッシュを、バックボーンカーブに沿ってインスタンス／スイープします。 | `input`, `curve` (+11 optional) |
| `view_vertex_order` | SideFX Labs View Vertex Order — 入力ジオメトリ（入力0）に頂点順序の可視化を注釈付けします：エレメントごとの色に加えて任意の順序矢印を付け、ソースジオメトリをそのまま通します。 | `input` (+5 optional) |
| `box_clip` | SideFX Labs Box Clip — `input`（入力0）を軸整列ボックスに対してクリップし、有効な側の平面を生き延びたジオメトリを保持します（各neg*/pos*トグルが6つのクリップ平面の1つをオンにし、6つすべてがデフォルトでオン）。size/center（_x/_y/_z経由のvec3）とscaleがクリップボックスのサイズと位置を決めます — すべてを保持するにはジオメトリより大きく、トリムするには小さくしてください。fillholesはカット面をキャップします。 | `input` (+16 optional) |
| `boxcutter` | SideFX Labs BoxCutter — `input`（入力0）のためのブーリアンボックスカッター：変形可能なボックスをメッシュに対して減算、粉砕、または合併します。boolean_opが操作を選び、bevel_divisions/bevel_distanceは切断ボックスを丸め、translate/rotate/scale（_x/_y/_z経由のvec3）が位置とサイズを決め、copies（＋copy_translate/copy_rotate vec3）はカットを配列します。 | `input` (+20 optional) |
| `boxcutter_subutil` | SideFX Labs BoxCutter Sub-Utility — boxcutterの土台となる単一形状のブーリアンボックスカッターで、`input`（入力0）に対して単独でも使えます。operationはsubtract/shatter/unionを選び、translate/rotate/scale（_x/_y/_z経由のvec3）がボックスを配置し、distanceはカットを押し出し、divisionsはその角をベベルし、copies（＋copy_translate/copy_rotate vec3）はそれを配列します。activeが有効／無効を切り替え、無効時はメッシュをそのまま通します。 | `input` (+21 optional) |
| `mesh_slice` | SideFX Labs Mesh Slice — `input`（入力0）を、軸整列した切断平面のグリッド（軸ごとにdivisions_x/_y/_z枚）でスライスし、（fill_holesで）カット面をキャップして、分離可能なピースを生成します。isolate_index + indexは1ピースのみを保持します。 | `input` (+7 optional) |
| `polyslice` | SideFX Labs PolySlice — `input`（入力0）を、center（vec3）、size（vec3）、scale、rotate（vec3）で位置／向きを与えたnum_slices枚の平行平面でスライスします。modeはスライスされたポリゴンかポリラインの断面かを出力します。connectivityはスライスされたピースのグループ化を決め、divide_convexは結果の非凸面を三角形化します。 | `input` (+25 optional) |
| `split_prim_by_normal` | SideFX Labs Split Prim by Normal — `input`（入力0）のプリミティブのうち、法線が`axis`方向の選んだ`direction`にspread_angle度以内で向いているものを選択します。invertは選択を反転します。 | `input` (+5 optional) |
| `polyscalpel` | SideFX Labs PolyScalpel — 必須の`cutter`ジオメトリ（入力1）がソースメッシュ`input`（入力0）と交差する箇所すべてでそれをスライスします。cutting_geo_typeはカッターの種類（points / polylines / polygon_surfaces）と一致していなければならず、input_geo_typeはソースと一致します。surface_outputはエッジ上の点かスライスされた面かを選び、slicing_methodは正確なPolySplitかより高速なBoolean-Shatter経路かを選びます。source_group/cutting_groupは各側を限定するジオメトリグループ名です。 | `input`, `cutter` (+14 optional) |
| `calculate_occlusion` | SideFX Labs Calculate Occlusion — アンビエントオクルージョン／キャビティ解析：面（および入力1の任意の`occluder`）に対してレイキャストし、オクルージョン値をポイントアトリビュート`occattr`へ書き込みます（`colorout`が有効なら表示`Cd`も）。 | `input` (+14 optional) |
| `calculate_slope` | SideFX Labs Calculate Slope — 表面の傾斜（各点の法線がアップ軸となす角度）を計算し、ポイントアトリビュート`sSlopeAttribute`へ書き込みます（`bSlopeCd`が有効なら表示`Cd`も）。 | `input` (+8 optional) |
| `calculate_thickness` | SideFX Labs Calculate Thickness — ポイントごとに`numrays`本の内向きレイを飛ばして局所的なメッシュの厚みを測り、その距離をポイントアトリビュート`attrname`へ書き込みます（デフォルト`thickness`。`outputcolor`が有効なら表示`Cd`も）。 | `input` (+10 optional) |
| `distance_from_border` | SideFX Labs Distance From Border — 各点について最も近い開いた境界／ボーダーエッジまでの距離を計算し、ポイントアトリビュート`distattr`へ書き込みます（`bDistanceAsColor`が有効なら表示`Cd`も）。 | `input` (+11 optional) |
| `edge_color` | SideFX Labs Edge Color — 凸エッジ対凹エッジを強調する表示`Cd`を書き込みます（エッジダメージマスクを駆動するのに使う摩耗／曲率の可視化）。 | `input` (+8 optional) |
| `fast_gaussian_curvature` | SideFX Labs Fast Gaussian Curvature — 離散ガウス曲率（角度欠損）をポイントアトリビュート`attribname_curv`（デフォルト`curvature`）へ、加えて角度を`attribname_angle`へ計算します。 | `input` (+11 optional) |
| `measure_curvature` | SideFX Labs Measure Curvature — 表面の曲率をポイントアトリビュート`convexityattr`（デフォルト`convexity`）と`concavityattr`（デフォルト`concavity`）へ測り、`viscolor`が有効なら表示`Cd`も出します。 | `input` (+13 optional) |
| `physical_ambient_occlusion` | SideFX Labs Physical Ambient Occlusion — 物理ベースのAOを、ポイントアトリビュート`outputattrib`（デフォルト`ao_mask`。加えて表示`Cd`）へベイクします。 | `input` (+18 optional) |
| `spectral_feature_extract` | SideFX Labs Spectral Feature Extract — スペクトル（拡散／PDE）フィーチャー解析：入力ポイントアトリビュートからマルチスケールのフィーチャーを抽出し、ポイントアトリビュート`outattrib_f`（デフォルト`extracted_float`）と`outattrib_v`（デフォルト`extracted_vec`）へ書き込みます。 | `input` (+19 optional) |
| `validate_geometry_type` | SideFX Labs Validate Geometry Type — パイプラインのガード：入力ジオメトリをそのまま通しつつ、それに関するルールをアサートし、ルールが失敗するとメッセージ／警告／エラーを発します。 | `input` (+5 optional) |
| `autouv` | SideFX Labs Auto UV — ワンクリックの自動UV：メッシュを自動シーム化し、各アイランドをフラット化（SCP/ABF）してから、アトラスへパックします。 | `input` (+25 optional) |
| `uv_unwrap_cylinder` | SideFX Labs UV Unwrap Cylinder — パイプ／チューブ／手足のための円筒UVアンラップ。 | `input` (+7 optional) |
| `inside_face_uvs` | SideFX Labs Inside Face UVs — 破砕されたメッシュの内側（「inside」）の面にUVをフラット化し、破砕内部にテクスチャを付けられるようにします。 | `input` (+9 optional) |
| `automatic_trim_texture` | SideFX Labs Automatic Trim Texture — メッシュのUVアイランドを、非インタラクティブにトリムシートアトラスへフィットさせます。 | `input`, `trim` (+10 optional) |
| `calculate_uv_distortion` | SideFX Labs Calculate UV Distortion — UVレイアウトが各エレメントを3Dに対してどれだけ伸縮させているかを測り、`distortionattribute`（デフォルトuv_distortion）へ書き込みます。 | `input` (+5 optional) |
| `merge_small_islands` | SideFX Labs Merge Small Islands — 相対面積が`cutoff`未満のUVアイランドを隣接アイランドへマージして再フラット化し、よりクリーンなパッキングのためにアイランド数を減らします。 | `input` (+7 optional) |
| `remove_uv_distortion` | SideFX Labs Remove UV Distortion — 歪んだ頂点（「peaks」）を内へ押し、潰れた頂点（「holes」）を外へ引くことで、UVの伸びを反復的に緩和します。 | `input` (+13 optional) |
| `texel_density` | SideFX Labs Texel Density — 与えられた`texturesize`について、UV付きメッシュ全体の単位あたりテクセル数を測り、（任意で）均一化します。 | `input` (+9 optional) |
| `uv_remove_overlap` | SideFX Labs UV Remove Overlap — 0-1タイル内で重なるUVアイランドを（`resolution`でラスタライズして）検出し、`repairoverlaps`が有効なときはそれらを引き離します。任意で問題のあるプリムをグループ化します。 | `input` (+6 optional) |
| `uv_unitize` | SideFX Labs UV Unitize — 各プリミティブ（または各UVアイランド）を、そのUVが0-1の単位正方形を満たすよう再マッピングします — トリムシート／タイリングテクスチャのワークフローの標準的な準備です。 | `input` (+8 optional) |
| `building_from_patterns` | SideFX Labs Building From Patterns — フロア／モジュールのパターングラマーを使って、ブロックアウト上に建物モジュールを配置します。 | `input` (+17 optional) |
| `building_generator` | SideFX Labs Building Generator — 3Dブロックアウトをフロアへスライスし、モジュールでスキンします。 | `input` (+20 optional) |
| `building_module` | SideFX Labs Building Module（labs::building_generator_utility） — 入力メッシュを、building_generator / building_from_patternsが消費する再利用可能な建物モジュール（名前、重み、優先度、バウンディングボックス）としてタグ付けします。 | `input` (+9 optional) |
| `pathfinding_global` | SideFX Labs Pathfinding Global — 地形上で集落の端点間の最小コスト経路を計算します。 | `input`, `terrain` (+12 optional) |
| `road_generator` | SideFX Labs Road Generator — 入力の道路カーブ（中心線）から、交差点付きの道路面メッシュを構築します。 | `input` (+19 optional) |
| `settlement_connections` | SideFX Labs Settlement Connections — 集落の点を道路ネットワークグラフへ接続し、角度／距離／数で接続をフィルタリングします。 | `input` (+13 optional) |
| `cable_generator` | SideFX Labs Cable Generator — 垂れ下がるケーブル／ワイヤーのメッシュを構築します。 | `input` (+26 optional) |
| `lot_subdivision` | SideFX Labs Lot Subdivision — 2Dポリゴンのブロックを、建物の区画へ再帰的に細分化します。 | `input` (+11 optional) |
| `scifi_panels` | SideFX Labs Sci-Fi Panels — メッシュをパネリングでグリーブル化します：面を区画へ細分化してから、切り欠き／ベベル付きの縁取りパネルを押し出します。 | `input` (+22 optional) |
| `simple_rope_wrap` | SideFX Labs Simple Rope Wrap — ロープ／ケーブルジオメトリをポリゴン面上にスイープし、ジオメトリオブジェクトのまわりに巻き付けます。 | `input`, `geometry` (+20 optional) |
| `mesh_tiler` | SideFX Labs Mesh Tiler — 単位タイル境界をまたぐパックドジオメトリを、シームレスにタイル化するようラップします（一方の端から出るピースが反対の端から再入します）。 | `input` (+9 optional) |
| `dirtskirt` | SideFX Labs Dirt Skirt — オブジェクト（`input`、入力0）が地面（`ground`、入力1）と接する箇所に、散布された土／デブリのスカートを構築します — 岩／壁の基部にできる小さな瓦礫の山です。obj*はオブジェクトを駆け上がるノイズ帯を、gnd*は地面に広がる帯を制御し、finalcountは散布デブリ数の上限、iterationsは帯を成長させ、thresholdはそれをトリムします。 | `input`, `ground` (+17 optional) |
| `snow_buildup` | SideFX Labs Snow Buildup — 入力された面（`input`、入力0）の上向きの部分に雪のシェルを堆積させます。angleは雪を保持する最大の面傾斜、baseheight/snowheightは深さを設定し、typenoiseは表面の見た目（drifts / melted / shoveled）を選び、smoothiterationsはそれを柔らかくします。snow_onlyは雪のグループのみを出力します。 | `input` (+20 optional) |
| `tree_branch_placer` | SideFX Labs Tree Branch Placer — 親の幹から枝を成長／配置します。 | `input` (+25 optional) |
| `tree_hierarchy` | SideFX Labs Tree Hierarchy — 下流の選択、風、エクスポートのために、木の枝に名前付きの世代／枝の階層（例：gen_0/_branch_1）をタグ付けします。 | `input` (+6 optional) |
| `cluster_refine` | SideFX Labs Cluster Refine — 接続された領域をクラスタリングし、クラスター境界を緩和してシームがきれいに読めるようにすることで、メッシュを溶接されたアイランドへ精緻化します。 | `input` (+8 optional) |
| `edge_damage` | SideFX Labs Edge Damage — VDBパスによって、プロシージャルな摩耗を加えるためにハードエッジを欠け／侵食させます。すべての変位は法線に沿ってプロシージャルであり、ディスク画像からではありません。 | `input` (+14 optional) |
| `edge_smooth` | SideFX Labs Edge Smooth — メッシュのエッジを緩和／スムージングし（任意で非共有／境界エッジのみ）、ベベル／ブーリアンされたジオメトリのファセットを整えます。 | `input` (+7 optional) |
| `mesh_sharpen` | SideFX Labs Mesh Sharpen — 曲率場に沿って点を押すことで表面のフィーチャーをシャープ化し、任意のスムージングパスを伴います。スキャンされた／柔らかいジオメトリを強調します。 | `input` (+12 optional) |
| `soften_normals` | SideFX Labs Soften Normals — カスプ角で頂点法線を再計算し、角度未満のエッジはなめらかに、よりシャープなエッジはハードのままに読ませます。加えてUVシームをまたいで法線をハード化することもできます。 | `input` (+3 optional) |
| `extract_borders` | SideFX Labs Extract Borders — メッシュの開いた境界エッジ（および任意でUVアイランドの境界）を、ポリラインまたはカーブとして抽出します。 | `input` (+4 optional) |
| `extract_silhouette` | SideFX Labs Extract Silhouette — ビュー軸に沿ってメッシュの外側シルエットをトレースし、カーブとして出力します（切り抜きカード／トリム形状）。 | `input` (+6 optional) |
| `straight_skeleton_2d` | SideFX Labs Straight Skeleton 2D — 平面ポリゴン／カーブの2Dストレートスケルトン（中心軸に似たトポロジカルなスパイン）を計算します。屋根／インセットや形状解析に有用です。 | `input` (+7 optional) |
| `straight_skeleton_3d` | SideFX Labs Straight Skeleton 3D — ボクセル化ソルブによって、閉じたメッシュの3Dストレートスケルトン／中心カーブネットワークを抽出します。 | `input` (+5 optional) |
| `dissolve_flat_edges` | SideFX Labs Dissolve Flat Edges — （ほぼ）同一平面の面の間のエッジを除去してシルエットを変えずにメッシュを簡略化し、任意でインライン（共線）の点も除去します。 | `input` (+8 optional) |
| `remove_inside_faces` | SideFX Labs Remove Inside Faces — 外から決して見えない内部／遮蔽された面（例：重なり合うブーリアンされたキットバッシュジオメトリ）を削除し、ポリゴン数を減らします。 | `input` (+6 optional) |
| `path_deform` | SideFX Labs Path Deform — `input`（入力0、メッシュ）を必須の`curve`（入力1、パス）に沿って曲げます。任意の`banking_curve`（入力2）がアップ／バンク方向を設定します。 | `input`, `curve` (+12 optional) |
| `polydeform` | SideFX Labs PolyDeform — 高詳細の`input`（入力0、source_mesh）を、スカルプト／編集された`target`（入力1、target_mesh）に追従するよう変形させ、低解像度の変形をフル解像度のメッシュへ転写します。 | `input`, `target` (+10 optional) |
| `sine_wave` | SideFX Labs Sine Wave — `input`（入力0）を、`axis`（X\|Y\|Z）に沿った2つの正弦波の和で変位させます。 | `input` (+14 optional) |
| `decal_projector` | SideFX Labs Decal Projector — デカール（ベースカラー＋ハイトマップ）を面`input`（入力0、Projection Mesh）へ投影します。 | `input` (+21 optional) |
| `detail_mesh` | SideFX Labs Detail Mesh — スタンプ／ディテールメッシュ`tile`（入力1）を、面`input`（入力0、キャンバス）のUVレイアウト全体にタイル状に敷き、タイルをそれにラップします（例：壁の上のレンガ／こけら板）。 | `input`, `tile` (+10 optional) |
| `triplanar_displace` | SideFX Labs Triplanar Displace — メッシュにトライプラナー投影した変位`texture`をサンプリングして、`input`（入力0）を変位させます（UV不要）。 | `input` (+22 optional) |
| `align_and_distribute` | SideFX Labs Align and Distribute — `input`（入力0）をピースへ分割し（`split_by`の接続性またはピース`attribute_name`で）、任意で`sort_by`（面積／ポリゴン数／`seed`付きランダム）し、`layout`（linear\|grid）内で`spacing`をとって並べます。 | `input` (+14 optional) |
| `delight` | SideFX Labs Delight — `input`（入力0）の頂点カラー（Cd）からベイクされた照明／AOを除去し、スキャン／撮影されたメッシュを均一なアルベドへ平坦化します。 | `input` (+11 optional) |
| `straighten` | SideFX Labs Straighten — 与えられた`grouptype`（primitive\|point\|edge）の選んだ`up_group`（および`align_forward`が有効なときは任意の`forward_group`）をアップ／フォワードの基準として使い、`input`（入力0）を正準的な軸整列フレームへ再配向します。`invert_up`はアップ軸を反転します。 | `input` (+8 optional) |
| `axis_align` | SideFX Labs Axis Align — `input`（入力0）を軸ごとに原点に対して再配置します：`x`/`y`/`z`のそれぞれが、その軸を変えないか、バウンディングボックスのCenter／Min／Maxを0へスナップするかを選びます。 | `input` (+5 optional) |
| `turntable` | SideFX Labs Turntable — `input`（入力0）を現在のフレームの関数として`axis`（X\|Y\|Z）まわりに回転させ、フレーム範囲にわたって`num_turns`回転を完了します（ターンテーブルのプレビューアニメーション）。 | `input` (+4 optional) |
| `chaotic_shapes` | SideFX Labs Chaotic Shapes — カオス的（ストレンジアトラクター）系からトレースしたポイントクラウドを持つ新規の/obj geoです。 | `name` (+8 optional) |
| `mandelbulb_generator` | SideFX Labs Mandelbulb Generator — 3Dのマンデルバルブフラクタルを持つ新規の/obj geoです。 | `name` (+10 optional) |
| `wang_tiles_sample` | SideFX Labs Wang Tiles Sample — 確率的なWangタイルサンプリング（後でWang Tiles Decoderが展開する非周期タイリングのシードセット）を持つ新規の/obj geoです。 | `name` (+3 optional) |
| `wfc_initialize` | SideFX Labs WFC Initialize — WFCのsample/paintツールが後で解く、空白の波動関数崩壊グリッド（`rows` x `cols`、各1024以下にクランプ）を持つ新規の/obj geoです。 | `name` (+4 optional) |
| `wang_tiles_decoder` | SideFX Labs Wang Tiles Decoder — Wangタイルの点グリッド（`input`、入力0。例：wang_tiles_sampleの出力）を、`rows` x `cols`の非周期タイリングへデコードします。 | `input` (+6 optional) |
| `connectivity_and_segmentation` | SideFX Labs Connectivity and Segmentation — 入力ポリゴン（`input`、入力0）をセグメントへ分割し、セグメントIDを`segmentattrib`へ書き込みます。 | `input` (+15 optional) |
| `multi_bounding_box` | SideFX Labs Multi Bounding Box — 入力メッシュ（`input`、入力0）にバウンディングボックスを構築します。 | `input` (+5 optional) |
| `wavefunction_collapse_2d` | SideFX Labs 2D Wave Function Collapse — 小さな色／タイルのサンプルに局所的に似た、より大きな2Dタイリングを合成します。 | `input`, `sample` (+9 optional) |
| `wfc_sample_paint` | SideFX Labs WFC Sample Paint — 波動関数崩壊ワークフローのペイントフロントエンド：`input`（入力0）＝WFCグリッド（wfc_initializeの出力）、任意の`modules`（入力1）＝タイル／モジュールセット。 | `input` (+6 optional) |
| `unreal_worldcomposition_prepare` | SideFX Labs Unreal World Composition Prepare — 入力された地形／メッシュ（`input`、入力0）をUnreal World Composition用にタグ付けします。クックされたSOP出力そのものがタグ付けされたジオメトリです。tilenumはタイル数を設定し、levelpath/materialpathはUnrealのコンテンツパスで、文字列アトリビュートとして書き込まれます（ファイルシステムパスではありません）。 | `input` (+12 optional) |
| `ml_cv_directory_import` | SideFX Labs ML CV Directory Import — ファイル名パターンに一致するディレクトリからアセットジオメトリをインポートするソースノード（入力0個）で、コンピュータービジョンの合成データ準備の入口です。 | `name` (+4 optional) |
| `ml_cv_keypoint_metadata` | SideFX Labs ML CV Keypoint Metadata — キーポイントのグラウンドトゥルースメタデータ（キーポイント半径、3D位置、スケルトン接続性）を入力ジオメトリに割り当て、姿勢推定の訓練データにします。 | `input` (+7 optional) |
| `ml_cv_label_metadata` | SideFX Labs ML CV Label Metadata — ジオメトリ（またはグループ）に、カテゴリID／名前と任意のインスタンスIDをタグ付けし、セグメンテーション／検出の訓練用にします。 | `input` (+10 optional) |
| `ml_cv_promote_synth_attribute` | SideFX Labs ML CV Promote Synth Attribute — 合成データアトリビュートを、あるジオメトリクラスから別のクラスへ（例：primitive → point）、選んだ集約方法で昇格させ、ラベルが正しいエレメントに載るようにします。 | `input` (+6 optional) |
| `ml_cv_rop_annotation_output` | SideFX Labs ML CV Annotation Output — 入力の合成フレームについて、COCO形式のJSONアノテーション（カテゴリ／インスタンスID、バウンディングデータ）を書き出す、ワイヤー接続のみのライターです。 | `input` (+10 optional) |
| `ml_cv_texture_mask` | SideFX Labs ML CV Texture Mask — テクスチャインスタンスIDとカテゴリID／名前を入力ジオメトリに割り当て、レンダリングされたテクスチャ領域が合成データセット内のラベル付きマスクになるようにします。 | `input` (+4 optional) |
| `ml_cv_vector_data` | SideFX Labs ML CV Vector Data — 合成フレームについて、ポイントごとのベクトルデータ（例：ソース点からのスクリーン空間の動き／方向ベクトル）を計算します。 | `input` (+5 optional) |
| `ml_cv_visualize_keypoints` | SideFX Labs ML CV Visualize Keypoints — 合成データのラベルを検査するために、キーポイントメタデータのジオメトリからキーポイント／スケルトン接続性のガイドジオメトリを構築します。 | `input` (+6 optional) |
| `export_uv_wireframe` | SideFX Labs Export UV Wireframe — ワイヤー接続のみ：入力メッシュのUVレイアウト（ワイヤーフレーム＋アイランド塗り）を画像ファイルへレンダリングします。 | `input` (+10 optional) |
| `udim_tile_number` | SideFX Labs UDIM Tile Number — 各エレメントのUVからそのUDIMタイル番号を計算し、アトリビュート（デフォルト`udim_tile`）へ書き込みます。 | `input` (+5 optional) |
| `visualize_uvs` | SideFX Labs Visualize UVs — メッシュのUVのための検査ジオメトリを構築します：チェッカーテクスチャマップのプレビューを適用し、UVアイランド＋シームを描画できます。 | `input` (+9 optional) |
| `testgeometry_luiz` | SideFX Labs Test Geometry（Luiz） — プロトタイピング用に、既製のテスト／ショーケースメッシュ（「Luiz」アセット）を構築するソースノード（入力0個）です。 | `name` (+1 optional) |
| `testgeometry_paul` | SideFX Labs Test Geometry（Paul） — プロトタイピング用に、既製のテスト／ショーケースメッシュ（「Paul」アセット）を構築するソースノード（入力0個）です。 | `name` (+1 optional) |
| `houdini_icon` | SideFX Labs Houdini Icon — Houdiniロゴをメッシュジオメトリとして構築するソースノード（入力0個）で、任意で押し出します。 | `name` (+2 optional) |
| `simple_retime` | SideFX Labs Simple Retime — アニメーションした入力を、全体の速度乗数でリタイムします（フレームごとのリタイムRampはHDAのデフォルトのままです）。 | `input` (+2 optional) |
| `resample` | カーブ／ポリラインを均一なセグメントへリサンプルします（resample SOP）。 | `input` (+14 optional) |
| `trail` | 時間にわたるモーショントレイル／接続性（trail SOP）：フレームをまたいで点をトレイルし、それらをメッシュ／ポリゴンとして接続するか、動きから速度を計算します。 | `input` (+14 optional) |
| `timeshift` | 上流のジオメトリをリタイムします — 入力SOPを、プレイバーが別のフレーム／時刻にあるかのように評価します（timeshift SOP）。method=byframeは`frame`を読み（integer_framesのスナップ付き）、method=bytimeは`time`を秒で読みます。clampは範囲外で最初／最後のフレームにサンプルを保持します。 | `input` (+6 optional) |
| `polyframe` | エレメントごとの向きフレーム — タンジェント（tangentu）、法線（N）、従法線（tangentv）アトリビュート — をカーブまたはサーフェス上に構築します（polyframe SOP）。 | `input` (+13 optional) |
| `fuse` | 一致する点を溶接／スナップします（Fuse 2.0） — heightfield_tilesplit、boolean、スキャンタイルのマージの後のシームクリーンアップの主力です。distanceは3Dのスナップ許容値（ワールド単位）：その範囲内の点は1つに統合され、タイル間の亀裂を閉じます。snap_typeはdistancesnap（近接、デフォルト）、gridsnap（グリッドへスナップ）、またはspecified（ターゲットアトリビュート経由でスナップ）を選びます。delete_degenerateは点のマージで潰れる面積／長さゼロのプリムを落とし、delete_unusedは孤立した点を除去し、consolidateはスナップされた点を単一の点へマージします（デフォルトで有効）。 | `input` (+6 optional) |
| `normals` | Normal SOP経由で法線を再計算（または反転）します。mode＝N アトリビュートがどのクラスに書き込まれるか：point（スムーズシェーディング、デフォルト）、vertex（面コーナーごと、ハード／ソフトエッジ）、prim（面ごとにフラット）またはdetail。cusp_angle（度）は角度より鋭いエッジでスムーズ対ファセットのシェーディングを分けます。reverseは法線の向きを反転し（裏返しのスキャン／ブーリアン面を修正）、normalizeは単位長を強制し、weightingは隣接面の法線をどう平均するかを選びます（0で面積による..2）。 | `input` (+6 optional) |
| `facet_smooth_subdiv` | opで多重化される3つのサーフェスオペレーター。facet（Facet SOP）：再ファセット／統合 — cusp_angleはエッジをシャープにし、unique_pointsは共有点を分割し（ハードなファセットの見た目）、make_planarは各面を平坦化します。smooth（Smooth SOP）：ポリゴンを追加せずに点の位置を緩和 — strengthはスムージング量（0..50）、methodはuniform\|scaledominant\|curvaturedominant、filter_qualityはパス数を上げます（1..5）。subdivide（Subdivide SOP）：ポリゴンを追加 — iterationsは細分化レベル（各レベルでポリゴン数が約4倍、なので3で既に64倍。ノードは3でソフトキャップ）、algorithmはスキームを選び（osdcc＝OpenSubdiv Catmull-Clark、スムーズサーフェスの標準）、close_holesは開いた境界を閉じます。 | `input` (+11 optional) |
| `lod_create` | opによるLOD／パックドプリミティブのステージング。lod（Labs LOD Create）：レベルオブディテールのチェーンを構築 — levelsはLODの数を設定します（その数の削減スロットを生成し、すべて100%から始まります。後でノード内でスロットごとのパーセンテージを調整してください）。pack（Pack SOP）：入力をパックドプリミティブ（フラットでメモリ軽量なインスタンシング単位）へ統合 — packbynameは名前アトリビュート値ごとに1プリムをパックし、transfer_attributes/transfer_groupsはパターンをパックドプリムへ運び、pivotはパックのピボット（origin\|centroid）を設定します。proxy（Pack SOP）：同じパックですが、パックドビューポートLOD（lodトークン、デフォルトbox）経由で安価なビューポートプロキシとしてステージングされます — 地形のset_tile_lodの一般ジオメトリ版です。 | `input` (+8 optional) |
| `assemble` | 名前付きピースをPackedFragmentプリミティブへパックします（Assemble SOP） — 破砕／名前付きメッシュの、レンダー／シム対応のパッキングです。packはデフォルトで有効（pack_geoが実際にパックドプリムを出すトグルです）。 | `input` (+14 optional) |
| `transform_pieces` | ピースごとのトランスフォームをパックドピースへ適用し直します（Transform Pieces） — シム結果→パックドジオメトリの往復です。 | `input` (+13 optional) |
| `for_each` | For-Eachループ／ピースごとの反復のスキャフォールド（block_begin＋パススルーの本体＋block_end、完全に配線・相互参照済み）を構築し、ジオメトリをピースごと、ポイントごと、または固定N回（カウントループ）で反復します。 | `input` (+14 optional) |
| `for_each_begin` | For-Eachのblock_beginを作成します — 合成可能なループの開始／入口です。 | `input` (+4 optional) |
| `for_each_end` | For-Eachのblock_endを作成します — 合成可能なループの終了／収集です。input＝ループ本体の出力（反復するノード）、begin＝対をなすblock_begin、pieces＝そのピース／ポイントをループするジオメトリです。 | `input` (+14 optional) |
| `compile_block` | ターゲットをCompile Block（compile_begin＋compile_end、相互参照済み）で包みます — 重いFor-Eachループを囲む、マルチスレッド／クックオーバーヘッド除去の最適化です（for_each_endのmultithreadをその中で設定してください）。 | `input` (+6 optional) |
| `feather_template` | Feather Template from Shape — フェザーレーンの入口。 | `name` (+10 optional) |
| `feather_template_assign` | Feather Template Assign — グルームをシードするために、スキン点にフェザーテンプレートを割り当てます。 | `input` (+7 optional) |
| `feather_template_interpolate` | Feather Template Interpolate — 疎なガイドフェザー＋テンプレートから、スキン全体にフェザーを補間して完全なグルームを育てます。 | `input` (+13 optional) |
| `feather_clump` | Feather Clump — 特徴的な分離した、絡み合ったフェザーの見た目のために、羽枝を分割してクランプします。 | `input` (+12 optional) |
| `feather_noise` | Feather Noise — フェザーに自然な乱れを加えます。 | `input` (+10 optional) |
| `feather_width` | Feather Width — レンダリングされるフェザーの太さを駆動する、羽軸と羽枝の幅を設定します。 | `input` (+6 optional) |
| `feather_resample` | Feather Resample — フェザーの羽軸と羽枝の点の解像度を変更します。 | `input` (+13 optional) |
| `feather_deintersect` | Feather Deintersect — 密なグルームがきれいに読めるよう、重なり合うフェザーを引き離します。 | `input` (+12 optional) |
| `feather_normalize` | Feather Normalize — フェザーアトリビュートを正準的なレスト形へ正規化します。 | `input` (+5 optional) |
| `feather_barb_transform` | Feather Barb Transform — 羽枝の位置を、フェザーローカル空間とオブジェクト空間の間で変換します。 | `input` (+3 optional) |
| `feather_deform` | Feather Deform — フェザーをスキンにキャプチャし、アニメーションするスキンとともに変形させます。 | `input` (+12 optional) |
| `feather_attrib_interpolate` | Feather Attrib Interpolate — ソースフェザーから、羽枝アトリビュートをフェザーへ補間します。 | `input` (+9 optional) |
| `feather_surface` | Feather Surface — 圧縮されたフェザーから、レンダリング可能なポリゴン面メッシュを構築します。 | `input` (+10 optional) |
| `feather_surface_blend` | Feather Surface Blend — フェザー面をターゲット面へブレンドします（例：翼を畳む）。 | `input` (+13 optional) |
| `feather_convert` | Feather Convert — 圧縮されたフェザーを、明示的なカーブまたはサーフェスジオメトリへ変換します。 | `input` (+9 optional) |
| `feather_uncondense` | Feather Uncondense — 圧縮されたフェザー（フェザーごとに1プリム）を、羽枝ごとの完全なカーブジオメトリへ展開します。 | `input` (+7 optional) |
| `feather_primitive` | Feather Primitive — 圧縮されたフェザープリミティブの表現（解像度＋命名）を編集します。 | `input` (+8 optional) |
| `feather_barb_tangents` | Feather Barb Tangents — フェザー上に羽枝ごとのタンジェントアトリビュートを計算します（一部の羽枝スタイリング／シェーディングオペが必要とします）。 | `input` (+1 optional) |
| `feather_min_dist` | Feather Minimum Distance — フェザー（入力0）とターゲットフェザー（入力3）の間の最小距離アトリビュートを計算します。 | `input` (+3 optional) |
| `feather_ray` | Feather Ray — フェザーをスキンまたはターゲットジオメトリへ投影／レイし、任意でヒット箇所のprimnum/primuvをサンプリングします。 | `input` (+10 optional) |
| `feather_visualize` | Feather Visualize — フェザーのビューポート可視化ジオメトリ（羽枝をカーブまたは面として）を生成します。 | `input` (+3 optional) |
| `hair_generate` | Hair Generate（hairgen::2.0） — スクリプト可能な髪／ガイドの生成器でありレーンの入口：スキン上にルートを散布してカーブを育て、任意でガイドセットから補間します。 | `input` (+17 optional) |
| `fur_setup` | Fur（fur） — オールインワンのレガシーFur生成器：スキンとガイドから、髪の生成＋クランプ＋分け目を1ノードで行います。 | `input` (+15 optional) |
| `hair_growth_field` | Hair Growth Field（hairgrowthfield） — 髪の成長フィールドを構築／頭皮からガイドルートを散布します。 | `input` (+14 optional) |
| `guide_initialize` | Guide Initialize（guideinit） — 新しく作成したガイドを配向します（風の形、リフト、スキンに沿ったブレンド）。 | `input` (+11 optional) |
| `guide_reguide` | Reguide（reguide） — ガイドセットを再配分／リサンプルします（ガイド密度とセグメント数を変更）。 | `input` (+11 optional) |
| `guide_fill` | Guide Fill（guidefill） — ガイド補間メッシュを使って、疎なガイドセットの隙間を埋めます。 | `input` (+7 optional) |
| `guide_grow_to_surface` | Guide Grow to Surface（guidegrowtosurface） — ガイドルートをターゲット面まで成長させます（ソース点をメッシュ上へ移流）。 | `input` (+10 optional) |
| `guide_process` | Guide Process（guideprocess） — 主要なガイドスタイリングのオペスタック：op1で単一の操作を選びます（方向／リフト／長さの設定、変位、ウェーブ化、ストレート化、スムージング、フリズ、ベンド、シムアトリビュート）。 | `input` (+15 optional) |
| `hair_clump` | Hair Clump（hairclump::2.0） — 髪／ガイドをストランドへクランプします（髪の代表的な見た目）。 | `input` (+15 optional) |
| `guide_clump_center` | Guide Clump Center（guideclumpcenter） — hair_clumpへ供給するクランプ中心のガイド／アトリビュートを計算します。 | `input` (+5 optional) |
| `guide_partition` | Guide Partition（guidepartition） — グルームを分け目領域へ分割する分け目線を作成します。 | `input` (+10 optional) |
| `guide_groom` | Guide Groom（guidegroom::2.0） — ブラシグルーマーのデータノードです。 | `input` (+13 optional) |
| `hair_comb` | Comb（comb） — ファー／ヘアの方向をとかします。 | `input` (+9 optional) |
| `guide_mask` | Guide Mask（guidemask） — 他のすべてのグルームオペが読み取るマスク（アトリビュート／グループ）を、ガイド／スキン上に作成します。 | `input` (+14 optional) |
| `guide_group` | Guide Group（guidegroup） — 命名規則によってガイド／分け目線のグループを作成します。 | `input` (+5 optional) |
| `guide_find_strays` | Guide Find Strays（guidefindstrays） — はぐれた／外れ値のガイドを検出し、グループ／アトリビュートにタグ付けします。 | `input` (+10 optional) |
| `guide_skin_attrib_lookup` | Guide Skin Attribute Lookup（guideskinattriblookup） — 保存されたskinprim/skinprimuvのルーティングを介して、スキンアトリビュートをガイドへコピーします。 | `input` (+9 optional) |
| `guide_tangent_space` | Guide Tangent Space（guidetangentspace） — 方向オペが必要とする、ガイドごとのタンジェント／法線／従法線／orientフレームを計算します。 | `input` (+12 optional) |
| `guide_interpolation_mesh` | Guide Interpolation Mesh（guideinterpolationmesh） — hair_generateがガイドを補間するのに使う補間メッシュ（リメッシュされたスキン＋ガイド重み）を構築します。 | `input` (+14 optional) |
| `guide_volume` | Guide Volume（guidevolume） — 多くのグルームオペが消費するガイド／スキンのボリューム表現（断面／シェル／リメッシュ／テト、任意でVDB）を構築します。 | `input` (+12 optional) |
| `guide_surface` | Guide Surface（guidesurface） — ガイド補間メッシュに沿って、ガイドから面を移動／構築します。 | `input` (+9 optional) |
| `guide_deform` | Guide Deform（guidedeform） — ガイドをスキンにキャプチャし、アニメーションするスキンとともに変形させます。 | `input` (+16 optional) |
| `guide_transfer` | Guide Transfer（guidetransfer） — グルームをソーススキンからターゲットスキンへ転写します。 | `input` (+11 optional) |
| `groom_blend` | Groom Blend（groomblend） — 2つの完全なグルーム（ガイドA対ガイドB）を重み／マスクでブレンドします。 | `input` (+14 optional) |
| `guide_collide_vdb` | Guide Collide With VDB（guidecollidevdb） — ガイドをコリジョンVDBの外へ押し出します。 | `input` (+11 optional) |
| `guide_advect` | Guide Advect（guideadvect） — ガイドを速度VDBを通して移流させるか、コリジョンを埋めます。 | `input` (+13 optional) |
| `hair_card_generate` | Hair Card Generate（haircardgen） — 髪のカーブから、テクスチャ付きのヘアカード（ゲーム／リアルタイム出力）を生成します。 | `input` (+16 optional) |
| `hair_volume_rasterize` | Volume Rasterize Hair（volumerasterizehair） — 髪のカーブを密度／色／タンジェントのVDBへラスタライズします（レンダー／シムの準備）。 | `input` (+10 optional) |
| `fiber_groom` | Fiber Groom（fibergroom） — 筋繊維のグルーミング（KineFXの筋肉レーンであり、髪ではありません）。 | `input` (+8 optional) |
| `volume_create` | Volume（volume） — 生成器：新規の/obj geoに、新しいスカラー／ベクトルのボリュームプリミティブを作成します（フォグ／密度のオーサリングソース）。type float/int、rank + componentsがボリュームのサイズを決め、volume_nameがグリッドを命名し、initialalphaが充填、zmin/zmax + use_cam_window/cameraがカメラフラスタムのボリュームを設定します（cameraはファイルではなくNodePathのシーン参照です）。 | `name` (+9 optional) |
| `vdb_create` | VDB（vdb） — 生成器：新規の/obj geoに、新しい空の型付きVDBグリッド（レベルセット／フォグ／ベクトル）を作成します — VDBのオーサリングソースです。grid_classは解釈を選び、grid_typeはボクセル型、grid_precisionはsingle/double、grid_nameがグリッドを命名します。 | `name` (+4 optional) |
| `volume_from_attrib` | Volume from Attribute（volumefromattrib） — ポイント／頂点アトリビュートをボリュームへラスタライズします。 | `input` (+14 optional) |
| `points_from_volume` | Points from Volume（pointsfromvolume） — フォグ／SDFボリュームの内部に点を散布します。 | `input` (+13 optional) |
| `paint_fog_volume` | Volume Paint Fog（paintfogvolume） — フォグボリュームへプロシージャルに密度を堆積させます。 | `input` (+15 optional) |
| `volume_rasterize_curve` | Volume Rasterize Curve（volumerasterizecurve） — カーブをフォグボリュームへラスタライズします（密度がカーブに沿って敷かれます）。 | `input` (+14 optional) |
| `volume_convert` | Convert Volume（convertvolume） — マーチングキューブによって、VDB／ボリュームをポリゴン面へ変換します。 | `input` (+7 optional) |
| `volume_surface` | Volume Surface（volumesurface） — フォグ／SDFボリュームの階層から、適応的なエッジ長でポリゴン面を構築します。 | `input` (+15 optional) |
| `extrude_volume` | Extrude Volume（extrudevolume） — ポリゴンを、ベース法線に沿ってソリッドなボリュームへ押し出します。 | `input` (+11 optional) |
| `convert_vdb_points` | Convert VDB Points（convertvdbpoints） — ポイントクラウドとVDB Pointsグリッドの間で変換します。 | `input` (+15 optional) |
| `volume_merge` | Volume Merge（volumemerge） — 完全なpre/postの加算・乗算スタックでボリュームをマージ／コンポジットします。 | `input` (+16 optional) |
| `vdb_merge` | VDB Merge（vdbmerge） — 名前が一致する複数のVDBグリッドを1つへマージします。 | `input` (+6 optional) |
| `volume_vector_join` | Volume Vector Join（volumevectorjoin） — 3つ（または4つ）のスカラーボリュームを1つのベクトルボリュームへ結合します。 | `input` (+8 optional) |
| `volume_vector_split` | Volume Vector Split（volumevectorsplit） — ベクトルボリュームを3つのスカラーボリュームへ分割します。 | `input` (+3 optional) |
| `volume_feather` | Volume Feather（volumefeather） — ボリュームの値を、その境界付近で柔らかく（フェザー）します。 | `input` (+12 optional) |
| `volume_ramp` | Volume Ramp（volumeramp） — ボリュームの値を、ソース→デストの範囲を通して再マッピングします。 | `input` (+8 optional) |
| `volume_noise_fog` | Volume Noise Fog（volumenoisefog） — 密度のディテール化のために、フォグボリュームへ層状のノイズを加えます。 | `input` (+14 optional) |
| `volume_noise_sdf` | Volume Noise SDF（volumenoisesdf） — サーフェスのディテール化のために、SDFボリュームへ層状のノイズを加えます。 | `input` (+14 optional) |
| `volume_adjust_fog` | Volume Adjust Fog（volumeadjustfog） — フォグボリュームの見た目を調整します（init／remapのコンボ）。 | `input` (+13 optional) |
| `volume_resample` | Volume Resample（volumeresample） — ボリュームを新しいボクセル解像度へリサンプルします。 | `input` (+10 optional) |
| `volume_resize` | Volume Resize（volumeresize） — ボリュームのグリッド範囲をリサイズ／再バウンドします。 | `input` (+10 optional) |
| `volume_reduce` | Volume Reduce（volumereduce） — ボリュームを集約値（max/min/average/median/sum/rms...）へ削減します。 | `input` (+8 optional) |
| `volume_bound` | Volume Bound（volumebound） — しきい値処理によって、ボリュームのアクティブ／バウンディング領域を再構築します。 | `input` (+4 optional) |
| `volume_sdf` | Volume SDF（volumesdf） — フォグ／マスクボリュームから符号付き距離場を計算します。 | `input` (+9 optional) |
| `vdb_activate_sdf` | VDB Activate SDF（vdbactivatesdf） — SDF VDBのナローバンドをアクティブ化／拡張します。 | `input` (+15 optional) |
| `vdb_topology_to_sdf` | VDB Topology to SDF（vdbtopologytosdf） — VDBのアクティブボクセルのトポロジーからSDFを構築します。 | `input` (+10 optional) |
| `vdb_occlusion_mask` | VDB Occlusion Mask（vdbocclusionmask） — 入力VDBの背後に、カメラに面するオクルージョンマスクVDBを構築します。 | `input` (+8 optional) |
| `volume_analysis` | Volume Analysis（volumeanalysis） — ボリュームの微分量を計算します。 | `input` (+4 optional) |
| `volume_velocity_from_curves` | Volume Velocity from Curves（volumevelocityfromcurves） — カーブに沿って流れる速度ボリュームを構築します。 | `input` (+17 optional) |
| `volume_velocity_from_surface` | Volume Velocity from Surface（volumevelocityfromsurface） — 面の動きから、速度（＋コリジョン）ボリュームを構築します。 | `input` (+9 optional) |
| `lattice_from_volume` | Lattice from Volume（latticefromvolume） — ボリュームのボクセルレイアウトに一致するラティス／ポイントグリッドを構築します。 | `input` (+7 optional) |
| `volume_deform` | Volume Deform（volumedeform） — ポイントデフォーム／移動ラティスによってボリュームを変形させます。 | `input` (+10 optional) |
| `volume_rasterize_lattice` | Volume Rasterize Lattice（volumerasterizelattice） — 移動するラティスをボリュームへラスタライズし直します。 | `input` (+15 optional) |
| `volume_break` | Volume Break（volumebreak） — SDFボリュームのカッターによって、ジオメトリをピースへ分割／破砕します。 | `input` (+12 optional) |
| `volume_splice` | Volume Splice（volumesplice） — タイル化されたボリュームのピースを1つのグリッドへスプライス／縫合します。 | `input` (+3 optional) |
| `volume_stamp` | Volume Stamp（volumestamp） — ソースボリュームを、点の位置でデスティネーションボリュームへスタンプします。 | `input` (+10 optional) |
| `volume_patch` | Volume Patch（volumepatch） — ボリュームの領域を別のボリュームでパッチします（ポアソンブレンド）。 | `input` (+9 optional) |
| `volume_convolve` | Volume Convolve（volumeconvolve3） — ボリュームに3x3x3の畳み込みカーネルを適用します。 | `input` (+4 optional) |
| `volume_fft` | Volume FFT（volumefft） — ボリュームの順／逆FFT（周波数領域）。 | `input` (+7 optional) |
| `volume_normalize` | Volume Normalize Weights（volumenormalize） — ボリュームの重み／値の集合を正規化します。 | `input` (+9 optional) |
| `volume_compress` | Volume Compress（volumecompress） — ボリュームのストレージを圧縮します（タイル／定数のプルーニング）。 | `input` (+15 optional) |
| `volume_arrival_time` | Volume Arrival Time（volumearrivaltime） — 速度ボリュームを通した、前面伝播の到達時間を計算します。 | `input` (+8 optional) |
| `volume_optical_flow` | Volume Optical Flow（volumeopticalflow） — 2つのボリューム間の動き（オプティカルフロー）を推定します。 | `input` (+11 optional) |
| `volume_trail` | Volume Trail（volumetrail） — 時間にわたって、速度ボリュームを通して点を移流／トレイルします。 | `input` (+16 optional) |
| `volume_ambient_occlusion` | Volume Ambient Occlusion（volumeambientocclusion） — ボリュームへアンビエントオクルージョンを計算します。 | `input` (+7 optional) |
| `volume_bake` | Bake Volume（bakevolume） — ボリュームへ照明／散乱をベイクします（レンダーの準備）。 | `input` (+11 optional) |
| `volume_noise_vector` | Volume Noise Vector（volumenoisevector） — ベクトルボリュームへ層状のノイズを加えます（速度のディテール化）。 | `input` (+9 optional) |
| `paint_color_volume` | Volume Paint Color（paintcolorvolume） — ボリュームへプロシージャルに色（Cd）を堆積させます。 | `input` (+15 optional) |
| `paint_sdf_volume` | Volume Paint SDF（paintsdfvolume） — SDFボリュームへプロシージャルに削り／追加します。 | `input` (+8 optional) |
| `vdb_convex_clip_sdf` | VDB Convex Clip SDF（vdbconvexclipsdf） — SDF VDBを、2つ目の凸SDFで凸クリップします。 | `input` (+7 optional) |
| `vdb_diagnostics` | VDB Diagnostics（vdbdiagnostics） — VDBグリッドを検証／診断します（データ専用のQC）。 | `input` (+15 optional) |
| `vdb_lod` | VDB LOD（vdblod） — VDBのためのレベルオブディテール（ミップ）ピラミッドを構築します。 | `input` (+6 optional) |
| `vdb_points_delete` | VDB Points Delete（vdbpointsdelete） — VDB Pointsグリッドから点を削除します。 | `input` (+5 optional) |
| `vdb_points_group` | VDB Points Group（vdbpointsgroup） — VDB Pointsグリッド内の点をグループ化します。 | `input` (+15 optional) |
| `vdb_rasterize_frustum` | VDB Rasterize Frustum（vdbrasterizefrustum） — パーティクルを、カメラフラスタムに整列したVDBへラスタライズします。 | `input` (+17 optional) |
| `vdb_visualize_tree` | VDB Visualize Tree（vdbvisualizetree） — VDBの内部ツリー構造の可視化ジオメトリを構築します。 | `input` (+15 optional) |
| `poly_patch` | カーブまたはメッシュのハル／ケージをまたいで、なめらかなポリゴンパッチ面を構築します（polypatch） — 粗いカーブケージを、クリーンでサブディブ対応の面へ整えます。basis＝スムージング基底（cardinal \| bspline）、connectivity＝ハルの行／列がどうパッチへ接続するか、divisions [u,v]＝出力解像度、close_u/close_vはそれをラップし、output_polygonsはメッシュプリミティブの代わりにポリゴンを出します。 | `input` (+8 optional) |
| `poly_loft` | 断面カーブの列をまたいで、ポリゴン面をスキンします（polyloft）。 | `input` (+11 optional) |
| `poly_spline` | ポリラインの点を通してなめらかなスプラインをフィットし、リサンプルされたポリゴンカーブとして再出力します（polyspline） — 粗いコントロールポリゴンをなめらかなカーブへ変えます。spline_type＝補間基底、closureは閉じるかどうか、division_methodはサンプル密度の分配方法、segment_length / divisions / sample_divisionsは出力解像度、tensionはCVのテンションです。 | `input` (+9 optional) |
| `circle_spline` | コントロールポリゴンを通して、円弧／楕円／ヘリックスのスプラインをフィットします（circlespline） — フリーフォームのスプラインでは得られない完全に丸い曲率を与えます。spline_type（hybrid \| circle \| ellipse \| helix）、helix_typeは巻き方、reparm_strengthは均一な間隔のために再パラメータ化し、segment_divisionsは出力解像度、output_tangent + tangent_attribはタンジェントアトリビュートを書き込みます。 | `input` (+8 optional) |
| `poly_cap` | 開いたポリゴン境界（非共有エッジ）をキャップポリゴンで埋めます（polycap） — チューブ／押し出しの端や穴のリングを塞ぎます。 | `input` (+7 optional) |
| `cap` | NURBS／メッシュ面と開いたカーブに、U/V境界ごとに端／極のキャップを追加します（cap） — チューブ／球／回転面の端を閉じます。first_u_cap / last_u_cap / first_v_cap / last_v_capのそれぞれがスタイル（none \| facet \| share \| round \| tangent）を選び、divisions_u / divisions_vは丸めキャップの解像度、scale_u / scale_vはキャップを膨らませます。 | `input` (+10 optional) |
| `fillet` | 隣接するプリミティブ／2つのカーブの間に、なめらかな遷移面を構築します（fillet） — 面の間のハードな接合を丸めます。 | `input` (+11 optional) |
| `stitch` | 2つの隣接する面ハルを、共有境界に沿ってブレンド／縫合します（stitch）。 | `input` (+12 optional) |
| `join` | 別々のプリミティブ（カーブまたは面）の列を、端から端へ1つの連続したプリミティブへ接続します（join） — 多数の小さなピースを1つの長いプリミティブへ変えます。 | `input` (+10 optional) |
| `poly_hinge` | ポリゴンをヒンジエッジまたは軸まわりに折り／回転させ、折り目をセグメントへ細分化します（polyhinge） — パネル、花びら、ポップアップの折りを開きます。group + group_type（primitive \| edge）が何を折るかを選び、pivot_modeはヒンジ線の定義方法、hinge_edgeはヒンジにするエッジ、hinge_angleは折り角、divisionsは折り目のセグメント、enable_inset + insetはベベルを追加し、output_front/back/sideは結果のシェルを切り替えます。 | `input` (+15 optional) |
| `poly_stitch` | 2つのポリゴンシェルの境界を溶接し、隙間をブリッジポリゴンで埋めます（polystitch） — シームを修復／別々にモデリングした半分を結合します。stitch_group / cornersはどの境界ポリゴン／点を縫合するかを制限し、toleranceは最大縫合距離、consolidateは一致する点を融合し、find_corners + corner_angleはコーナー点を自動検出します。 | `input` (+7 optional) |
| `poly_soup` | 多数のポリゴンを、1つの軽量な「polysoup」プリミティブへ統合します（polysoup） — 密な静的メッシュのメモリ＋ノードオーバーヘッドを削減します。インスタンシング／重いスキャッターのターゲットの前に最適です。groupはソースを制限し、min_polysはサイズしきい値、convexは凸ポリゴンへ三角形化し、use_max_sides + max_sidesはポリゴンの辺数を制限し、merge_verticesは同一の頂点を溶接し、ignore_attribs / ignore_groupsはプリムごとのデータを落とします。 | `input` (+9 optional) |
| `poly_cut` | ポリゴンを、点、エッジ、またはアトリビュートの交差に沿って切断／分割し、任意でカット領域を除去します（polycut）。groupは影響するポリゴンを制限し、type（points \| edges）はカットプリミティブ、cut_points / cut_edgesはカット位置を指定し、strategy（remove \| cut）は削除するか単に分割するか、cut_attrib + cut_value + cut_thresholdはアトリビュートがある値を横切る箇所で切断し（アイソカット）、keep_closedは結果を再び閉じます。 | `input` (+10 optional) |
| `poly_path` | ばらばらのエッジ／開いたポリラインを、クリーンで連続したパスへ再接続します（polypath） — 下流のスイープ／リサンプルのために、エッジ抽出や境界カーブを整えます。connect_endsは近くの端点を結合し（max_end_dist以内）、connect_only_to_endsは結合を他の端点のみに制限し（カーブ途中のT字接合なし）、close_loopsは孤立したリングを閉じます。 | `input` (+5 optional) |
| `convert_line` | ジオメトリのエッジをポリラインカーブへ変換します（convertline） — polywire、リサンプル、スイープのために、メッシュからワイヤーフレーム／エッジカーブを抽出します。groupはソースを制限し、connect_pathはエッジを連続したパスへ連鎖させ、keep_orderはグループ順を保ち、close_loopsは孤立したリングを閉じ、remove_unusedは孤立した点を落とし、compute_length + length_nameはプリミティブごとのレスト長アトリビュートを書き込みます。 | `input` (+8 optional) |
| `circle_from_edges` | 点／エッジのリングを、最良フィットの円へスナップします（circlefromedges） — ボルト穴、パイプ端、ホイールアーチを完全に丸くします。group + group_typeはリングを選び、only_boundaryはグループ境界のみを使い、explicit_radius + radiusは半径を強制し（そうでなければ最良フィット）、scaleはフィットした円を拡大／縮小し、output_edge_groupは結果のエッジを命名します。 | `input` (+8 optional) |
| `orient_along_curve` | カーブに沿って、ポイントごとの向きフレーム（タンジェント／アップ＋回転）を計算します（orientalongcurve） — スイープ、コピートゥカーブ、リボンのねじれのためのリグです。 | `input` (+17 optional) |
| `delta_mush` | 表面ディテールを保ちながら、変形したメッシュをスムージングします（deltamush） — でこぼこなスキニング／ジッターのある変形の標準的な修正です。 | `input` (+10 optional) |
| `surface_relax` | 束になった／伸びたトポロジーを緩和するために、面全体に点を均一に再配分します（surfacerelax） — 形状をほとんど変えずに点の分布を改善します。 | `input` (+4 optional) |
| `laplacian` | メッシュの離散ラプラス作用素（コタンジェント／平均値／Wachspress／Tutteの重み）を計算し、アトリビュートに疎行列として保存します（laplacian） — メッシュ拡散、スムージング、ジオメトリ処理ソルブの基盤です。modeは重み付けスキームを選び、separate_massは質量行列を分離し、diffusion + diffusion_coeffは代わりに拡散行列を構築し、epsilonは正則化します。 | `input` (+6 optional) |
| `soft_transform` | なめらかな放射状フォールオフで、点の領域を移動／回転／スケールします（softxform） — プロポーショナル編集／マグネットのグラブです。 | `input` (+9 optional) |
| `soft_peak` | なめらかな放射状フォールオフで、点を法線に沿って押します（softpeak） — ソフトなインフレート／へこみのブラシです。 | `input` (+7 optional) |
| `elastic_transform` | 材料を通して伝播するグラブ／ねじり／スケール／ピンチのハンドルによって、メッシュを弾性ソリッドとして変形させます（elastictransform） — 柔らかいゴムを引っ張るような感触です。 | `input` (+12 optional) |
| `magnet` | 距離とともに減衰するメタボール的なフィールドを持つ、移動する「マグネット」形状によって、`input`の点を変形させます（magnet） — プロキシ形状で駆動されるスカッシュ／ストレッチ、へこみ、筋肉の膨らみです。 | `input` (+11 optional) |
| `bulge` | 「マグネット」形状が重なる箇所で、`input`の点を法線に沿って外／内へ押します（bulge） — プロキシ形状で駆動される、高速で局所的な膨らみです。 | `input` (+7 optional) |
| `creep` | `input`ジオメトリを面のUV空間へ投影し、その面全体を這わせます（creep） — デカール／軌跡／テキストをメッシュに貼り付けるか、その上をジオメトリが滑るのをアニメーションさせます。 | `input` (+10 optional) |
| `vector_deform` | 2つの一致するポイントクラウド（レストセットと変形セット）の差によって`input`を変形させ、その動きの場をメッシュへ補間します（vectordeform） — 任意のドライバー点からのケージ／ラティス式の変形です。 | `input` (+9 optional) |
| `shrinkwrap` | `input`の点のまわりにタイトな凸包をラップします（shrinkwrap） — 高速なコリジョンプロキシ、バウンディングシェル、簡略化されたシルエット。type（xyz＝フル3Dハル \| xy＝2D平面ハル）、shrink_amountはハルを内側へインセットし、plane_origin / plane_normalは2Dモードの投影平面を定義し、preserve_attribsはソースアトリビュートを運び、remove_inline_pointsは共線のハル点を整えます。 | `input` (+8 optional) |
| `detangle` | 自己交差／相互貫入するジオメトリを引き離し、重なりを止めます（detangle） — 絡まったクロス、ヘア、群衆メッシュのクリーンアップです。 | `input` (+8 optional) |
| `tetrahedralize` | 閉じた入力面を、四面体（テト）メッシュで満たします（tetrahedralize） — FEM／ソフトボディ／有限要素の準備の入口です。 | `input` (+17 optional) |
| `tet_conform` | 面が入力ポリゴンに一致する、境界適合のテトメッシュを構築します（tetconform） — 面を尊重しなければならないときに、単なる充填より高品質な体積メッシュ化です。 | `input` (+17 optional) |
| `tet_embed` | 入力面を、より粗い背景テトラティスの内部に埋め込みます（tetembed） — 面適合メッシュではなく、詳細なジオメトリを囲むシミュレーション可能なテトケージが欲しいときの、高速なFEM／ソフトボディの準備です。 | `input` (+17 optional) |
| `tet_layer` | 面から、与えられた厚みの単一のテトレイヤーを構築します（tetlayer） — FEMのスキン／外皮のための素早い体積シェルや、開始のテト帯です。 | `input` (+7 optional) |
| `tet_partition` | 領域境界ポリゴンを使って、テトメッシュを名前付きピースへ分割します（tetpartition） — ソリッドをFEM領域／破砕チャンクへ切り分けます。 | `input` (+5 optional) |
| `tet_surface` | テトメッシュの外側の面ポリゴンを抽出します（tetrasurface） — 体積テトメッシュから、レンダリング／コリジョン可能なスキンを取り戻します。 | `input` (+4 optional) |
| `tet_strata` | 外側の面と内側の境界の間に、層状（成層）のテトシェルを構築します（tetstrata） — 多層のFEM材料（スキン／脂肪／筋肉の外皮、積層ソリッド）です。 | `input` (+9 optional) |
| `tet_fracture` | ボロノイ／パターン分割によって、ジオメトリをテトベースのチャンクへ破砕します（tetfracture） — FEM／RBD破壊のためにソリッドを事前破砕します。 | `input` (+7 optional) |
| `solid_embed` | 単一のエレメントスケールでサイズを決めたソリッドなテトラティスに、入力ジオメトリを埋め込みます（solidembed） — 1つのノブのFEMケージビルダーです。 | `input` (+2 optional) |
| `topo_transfer` | クリーンなテンプレートメッシュをターゲットメッシュ上へラップし、テンプレートのトポロジーをターゲットの形状へ転写します（topotransfer） — リグ済みのベースメッシュをスキャン／スカルプトに合わせる、リトポ／キャラクターの主力です。 | `input` (+18 optional) |
| `topo_slide` | 一致するリファレンス／ターゲットのカーブに導かれて、ターゲットメッシュの点をその面全体にスライドさせるか、カーブ導出のトポ転写を実行します（toposlidebycurverefs） — シーム／フィーチャーに沿ったリトポのフローをプロシージャルに調整します。 | `input` (+15 optional) |
| `usd_configure_sop` | SOPジオメトリがどうUSDへオーサリングされるかを設定します — ステージ全体のインポートオプションを、ジオメトリ上のUSDメタデータとして設定します（SOPコンテキストの`usdconfigure`。純粋なオペレーターで、ファイル書き込みはありません）。 | 9 optional |
| `usd_configure_geometry` | SOPジオメトリ上に、プリミティブごとのUSDジオメトリメタデータをオーサリングします（SOPコンテキストの`usdconfiguregeometry`。純粋なオペレーターで、ファイル書き込みはありません）。 | 9 optional |
| `usd_configure_prims_from_points` | 点からUSDプリムアトリビュートをオーサリングします — 点を、プリムごとのメタデータを持つ設定済みUSDプリム（球、ライト、xform…）へ変えます（SOPコンテキストの`usdconfigureprimsfrompoints`。純粋なオペレーターで、ファイル書き込みはありません）。 | 12 optional |
| `unpack_usd` | パックドUSDプリミティブを、ネイティブHoudiniジオメトリへアンパックします（unpackusd） — usd_import_sop（unpack=false）からの軽量なパックドプリムを、編集可能なポリゴン／点へ変えます。 | `input` (+14 optional) |
### グループとアトリビュート

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `attribute_normalize_float` | SideFX Labs Attribute Normalize Float — floatアトリビュートを、その入力値の範囲を用いて[out_min, out_max]（デフォルト0..1）へ再マッピングします。 | `input` (+10 optional) |
| `attribute_normalize_vector` | SideFX Labs Attribute Normalize Vector — vectorアトリビュートを正規化します。 | `input` (+11 optional) |
| `attribute_value_replace` | SideFX Labs Attribute Value Replace — アトリビュートをリネームし、かつ/または`attribute_list`（デフォルト`name`）で指定したアトリビュートに既定の初期値／フォールバック値を仕込みます。 | `input` (+8 optional) |
| `color_adjustment` | SideFX Labs Color Adjustment — colorアトリビュート（デフォルト`Cd`、またはカスタムアトリビュート）に対する明度／コントラスト／彩度／ガンマのグレーディング。 | `input` (+13 optional) |
| `color_blend` | SideFX Labs Color Blend — 2つのcolorアトリビュートを、Photoshop風の`blend_mode`でブレンドします。 | `input`, `input2` (+9 optional) |
| `color_gradient` | SideFX Labs Color Gradient — `axis`（X/Y/Z、または`rotation_angle`で回転させたCustom）に沿ったカラーグラデーションを`Cd`（またはカスタムアトリビュート）へ描き込みます。 | `input` (+7 optional) |
| `min_max_average` | SideFX Labs Min Max Average — アトリビュートを単一の統計量（`method`：max/min/mean/median/sum/rms/…）へ縮約し、`prefix`/`suffix`で命名したdetailアトリビュートとして書き戻します（`detail_attribute`をオフにすると要素ごとにプロモートされます）。 | `input` (+8 optional) |
| `radial_sort` | SideFX Labs Radial Sort — 軸（`*_dir`）まわりの角度で点および/またはプリミティブを並べ替え、ファン／リングがきれいな回転順にインデックスされるようにします。 | `input` (+16 optional) |
| `sort_geometry` | SideFX Labs Sort — 選択したキーで点および/またはプリミティブを並べ替えます：軸（byx/byy/byz）、ランダム（`*_seed`）、シフト（`*_offset`）、ベクトルに沿って（`*_dir`）、空間的近接、またはアトリビュート（`*_attrib`）による並べ替え。 | `input` (+17 optional) |
| `visualize_vector` | SideFX Labs Visualize Vector — vectorアトリビュート（`vector_attribute`、デフォルト`P`）から検査用の矢印ジオメトリを生成します。 | `input` (+18 optional) |
| `fast_group_unshared` | SideFX Labs Fast Group Unshared — 入力メッシュ（input 0）のUNSHARED（開いた境界／ボーダー）要素をグループ化します：単一のプリミティブが所有するエッジと、それらに接する点／プリミティブ／頂点。 | `input` (+4 optional) |
| `group_by_attribute` | SideFX Labs Group by Attribute — 入力（input 0）上のアトリビュートの異なる値ごとに1つのグループを作成します。 | `input` (+5 optional) |
| `group_by_measure` | SideFX Labs Group by Measure — 幾何学的な離心率の指標（プリミティブの形状が円／正方形からどれだけ外れているか）でプリミティブをグループ化します。 | `input` (+5 optional) |
| `group_curve_corners` | SideFX Labs Group Curve Corners — 入力カーブ（input 0）のコーナー点を、`inside`グループ（凸コーナー）と`outside`グループ（凹コーナー）へラベル付けします。 | `input` (+6 optional) |
| `group_grow` | SideFX Labs Group Expand — 既存のグループを、入力ジオメトリの接続性に沿って拡大（または縮小）します。 | `input` (+3 optional) |
| `group_invert` | SideFX Labs Group Invert — 名前付きグループをその場で反転します：列挙された各グループはその補集合（そこに含まれないすべての要素）で置き換えられます。 | `input` (+4 optional) |
| `loops_from_selection` | SideFX Labs Loops from Selection — シードとなるエッジグループから完全なエッジループ（またはクワッドループ）を伸ばします。 | `input` (+12 optional) |
| `random_selection` | SideFX Labs Random Selection — 入力要素のランダムな部分集合を選択し、それをグループにします。 | `input` (+24 optional) |
| `extract_filename` | SideFX Labs Extract Filename — 上流のFile SOP（`input`、または`input_mode`=customのときは`custom_file_sop`）からファイルパスを読み取り、その各部分（フルパス／ファイルパス／ファイル名／ディレクトリ）をdetailのstringアトリビュートへ書き込みます。 | `input` (+7 optional) |
| `group_create` | 名前付きで永続的な点／プリミティブ／エッジのグループを作成します（groupcreate） — あらゆる対象指定オペレーション（blast、グループのbevel、dissolve、グループのtransform）のためのセットアップ工程です。 | `input`, `group_name` (+10 optional) |
| `group_promote` | グループを要素クラス間で変換します（grouppromote） — 例：点グループ→プリミティブグループ、境界／unsharedオプション付き。 | `input` (+8 optional) |
| `group_range` | 数値インデックス範囲および/またはN個ごとのストライドで要素をグループ化します（grouprange） — ピースID部分集合の選択、行の交互抽出、決定論的なスライス。group_name = 作成するグループ。class：points\|prims\|vertices。method：absolute（インデックスstart..end）\| relative（全体に対する割合0..1）\| length \| partition（num_partitions個の均等なブロックに分割）。start/endがウィンドウを区切ります。select_amount（'of'）+ select_total（'every'）+ select_offsetでN個ごとのストライドを指定します（of=1 every=3 => 3個ごと）。invertはメンバーシップを反転します。mergeは既存の同名グループと結合します。 | `input` (+13 optional) |
| `group_expand` | エッジ接続のステップでグループを拡大または縮小します（groupexpand） — 負のステップは縮小します。 | `input` (+9 optional) |
| `group_transfer` | あるジオメトリから別のジオメトリへ、近接によってグループメンバーシップを転送します（grouptransfer）。 | `input` (+11 optional) |
| `group_delete` | グループ定義を削除します（ジオメトリはそのまま） — groupdelete。 | `input` (+3 optional) |
| `group_rename` | グループをリネームします（grouprename）。 | `input` (+4 optional) |
| `group_geo` | 深い幾何学的グループ選択（groupcreate） — group_createにないモード：バウンディングスフィア／オブジェクト／ボリューム／凸包、カメラによるバックフェイス、エッジ角度、unshared／開いたエッジ。 | `input` (+27 optional) |
| `blast` | グループによるジオメトリの削除 — 対象指定削除の基本プリミティブです。group = （グループツールが作った）グループ名／パターン、または生の要素範囲。group_typeが解釈を導きます（guess\|points\|prims\|edges\|breakpoints）。delete_non_selectedは反転します：グループのみを残し、それ以外をすべて削除します（isolateのイディオム）。fill_holeは残った穴を塞ぎます。remove_groupは後でグループタグを外します。 | `input`, `group` (+5 optional) |
| `attribute_transfer` | SOURCEメッシュから入力へ、近接によって点／プリミティブのアトリビュートを転送します（attribtransfer） — LIDARカラー／GISアトリビュートの主力：スキャンからリメッシュへCdをペイントする、トポロジー変更をまたいでN／uvを引き継ぐ。 | `input`, `source` (+4 optional) |
| `attribute_create` | 定数値を持つ型付きの点／プリミティブ／頂点／detailアトリビュートを作成します（attribcreate） — Cd/pscale/N/id/マテリアルインデックスや任意のカスタムアトリビュートを追加する、ラングルを使わない型付きの手段です。attrib_name = 作成するアトリビュート。type = ストレージ型（float\|int\|vector\|...）。class = 要素クラス。value = 数値または[x,y,z]（string型はvalueにテキストとして文字列を渡します）。size = タプルサイズ1..4。precision = ストレージのビット数。type_infoは変換のセマンティクスをタグ付けし、下流ノードがアトリビュートを正しく変換できるようにします（NにはNormal、CdにはColor、位置にはPoint）。on_existingは名前が既に存在する場合の挙動を決めます。groupは作成対象を制限します。 | `input`, `attrib_name` (+9 optional) |
| `attribute_promote` | アトリビュートを要素クラス間で移動／集約します（attribpromote） — 点アトリビュートをプリミティブごとの平均に変える、detail値を点に広げる、など。attrib = ソース名。from_class/to_class = point\|prim\|vertex\|detail。method = ソース値を1つの宛先要素へ集約する方法（max\|min\|mean\|mode\|median\|sum\|first\|last\|array...）。out_nameは結果をリネームします。piece_attribは名前付きピースごとに独立して集約します。delete_original：注意 — このノードはデフォルトでソースを削除します。両方を残すにはfalseを渡してください。 | `input`, `attrib` (+7 optional) |
| `attribute_delete` | クラス＋スペース区切りの名前パターンでアトリビュートを削除します（attribdelete） — エクスポートやソルバの前にCd/N/rest／一時アトリビュートを落とすための整理。point/prim/vertex/detailはそれぞれ削除する名前のスペース区切りパターンです（例："Cd N *rest*"）。negateは反転させます：リストしたパターンのみを保持し、それ以外をすべて削除します。 | `input` (+6 optional) |
| `attribute_cast` | アトリビュートのストレージ精度をキャストします（attribcast） — 重いポイントクラウド／地形タイル向けの、メモリを半減する32→16ビット最適化。class = 要素クラス。attribs = スペース区切りの名前パターン（デフォルト* = すべて）。precision = ターゲットのストレージ：わかりやすいfloatの16\|32\|64はfpreal16/32/64に対応し、整数キャストには明示的なノードトークン（uint8\|int8\|int16\|int32\|int64\|fpreal16\|fpreal32\|fpreal64\|preferred）を渡します。 | `input` (+4 optional) |
| `attribute_interpolate` | UVWまたはキャプチャされたウェイトを介して、ソースジオメトリから点／頂点へアトリビュートを補間します（attribinterpolate）。 | `input` (+16 optional) |
| `attribute_from_volume` | ボリューム／VDBフィールドを点アトリビュートへサンプリングします（attribfromvolume）。入力／出力のリマップ付き。 | `input` (+10 optional) |
| `attribute_blur` | サーフェス全体でアトリビュートを平滑化／リラックスします（attribblur） — ラプラシアン／体積保存、接続性または近接による。 | `input` (+15 optional) |
| `attribute_copy` | あるジオメトリから別のジオメトリへアトリビュートをコピーします（attribcopy）。任意でpieceのようなアトリビュートによるマッチング付き。 | `input` (+13 optional) |
| `attribute_randomize` | アトリビュートにランダム化した値を書き込みます（attribrandomize） — ramp／discrete（重み付き）／uniformdiscreteを含む全12種の分布。min_limit/max_limitは非有界の分布（normal/exponential/lognormal/cauchy）のみをクランプし、すでに有界な一様抽出はクランプしません。 | `input` (+26 optional) |
| `attribute_composite` | マージ／スタックしたストリームをまたいでアトリビュートをコンポジットします（attribcomposite） — mean/max/min/over/under。 | `input` (+9 optional) |
| `attribute_reorient` | vector／quaternionアトリビュートを、レスト／リファレンスに対する変形に追従するよう再配向します（attribreorient）。 | `input` (+6 optional) |
| `attribute_swap` | アトリビュートを別の名前へスワップ／コピー／移動します（attribswap）。 | `input` (+6 optional) |
| `assign_name` | ピース同一性のnameアトリビュートを割り当てます（Name SOP） — インポート／モデリングしたフラグメントを、assemble／RBDの前に整える必須の準備工程です。 | `input` (+7 optional) |
| `enumerate` | 要素ごとまたはピースごとのインデックス／nameアトリビュートを書き込みます（Enumerate SOP）。 | `input` (+8 optional) |
| `connectivity` | 接続された各ピースに連番のクラスIDアトリビュートを付与します（connectivity） — ピース単位のblast、サイズによるdespeckle、ピースごとのランダム化、assembleの入力になります。connect_type：point（エッジを共有する点）\| prim（点を共有するプリミティブ）。attrib_name = 出力IDアトリビュート。attrib_type：int \| string（stringは`prefix`を前置します、例：'piece_3'）。groupはラベリングをpoint/primグループに制限します。by_uvはUVシームを挟んで接続を分割します（uv_attribが必要）。 | `input` (+8 optional) |
| `measure` | 幾何学的な量をアトリビュートへ計算します（measure）。measure_type：perimeter\|area\|volume\|centroid\|curvature\|gradient\|laplacian\|boundaryintegral\|surfaceintegral。attrib_name = 出力。class：points\|prims — 結果を受け取るクラス。curvature_typeはmeasure_type=curvatureのときのみ適用されます。src_attribはgradient/laplacian/*integralが作用するアトリビュートを指定します（例：'height'フィールドの勾配）。total_attribは合計値（メッシュ全体またはピースごとの面積／体積）をdetailアトリビュートへ書き込みます。groupは制限します。 | `input` (+8 optional) |
| `group_combine` | 2つの名前付きグループを結果グループへブール結合します（groupcombine）。result = 新しいグループ名。group_a / group_b = 既存のソースグループ名。operation：union（いずれかに含まれる）\| intersect（両方に含まれる）\| xor（ちょうど一方に含まれる）\| subtract（Aに含まれBに含まれない）。group_type = 3つすべてのグループのクラス（guessは自動検出）。 | `input`, `result`, `group_a`, `group_b` (+3 optional) |
| `attrib_adjust_float` | 値パターンでfloatアトリビュートをオーサリング／変更します（attribadjustfloat）。 | `input` (+16 optional) |
| `attrib_adjust_integer` | 値パターンでintegerアトリビュートをオーサリング／変更します（attribadjustinteger）。 | `input` (+14 optional) |
| `attrib_adjust_vector` | vectorアトリビュートの方向および/または長さをオーサリング／変更します（attribadjustvector）。 | `input` (+13 optional) |
| `attrib_adjust_color` | color（Cd）アトリビュートをオーサリング／変更します（attribadjustcolor）。 | `input` (+11 optional) |
| `attrib_adjust_array` | arrayアトリビュートの同一性／順序の制御（attribadjustarray）。 | `input` (+6 optional) |
| `attrib_adjust_dict` | dictionaryアトリビュートの高レベルな制御（attribadjustdict）。 | `input` (+7 optional) |
| `attrib_combine` | 数学演算でアトリビュートを宛先へ結合します（attribcombine）。 | `input` (+12 optional) |
| `attrib_fill` | フィールドを解くことでアトリビュートをサーフェス全体に充填／伝播します（attribfill）。 | `input` (+13 optional) |
| `attrib_fade` | フレームにわたって立ち上がり／保持／立ち下がりする点ごとのフェードウェイトをオーサリングします（attribfade）。通常はパーティクル／ピースをフェードイン・アウトさせるために使います。 | `input` (+10 optional) |
| `attrib_remap` | 数値アトリビュートの値を入力範囲から出力範囲へ、任意でrampを介してリマップします（attribremap）。 | `input` (+11 optional) |
| `attrib_sort` | アトリビュートの値で点／頂点／プリミティブを並べ替えます（attribsort）。 | `input` (+7 optional) |
| `attrib_find` | 各要素について、SEARCHジオメトリ内でアトリビュート値が一致する要素を見つけます（attribfind）。 | `input` (+10 optional) |
| `attrib_from_map` | ソースをUVに沿って点アトリビュートへサンプリングします（attribfrommap）。 | `input` (+10 optional) |
| `attrib_from_parm` | 別のノードのパラメータ値を、アトリビュートとしてジオメトリへインポートします（attribfromparm）。 | `input` (+7 optional) |
| `attrib_from_pieces` | 名前付きピースをまたいでピースごとのアトリビュート値を割り当てます（attribfrompieces）。 | `input` (+11 optional) |
| `attrib_mirror` | ジオメトリの一方の側から他方へアトリビュートをコピー／ミラーします（attribmirror）。 | `input` (+13 optional) |
| `attrib_paint` | ペイント可能なアトリビュートをセットアップします（attribpaint）。 | `input` (+8 optional) |
| `attrib_string_edit` | stringアトリビュート値に対する検索／置換（attribstringedit）。 | `input` (+11 optional) |

### クリーンアップとメッシュ化

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `mesh_pointcloud` | ポイントクラウドをメッシュに変換します（cloud → VDB → polygons）。任意でリダクション、カラー転送、エクスポート付き。 | `name`, `input` (+6 optional) |
| `quad_remesh` | フィールド整列のクワッドリメッシュ（ネイティブのquadremesh SOP — Labs／サードパーティのライセンス不要）：三角形化／スキャンメッシュを、サブディビジョンやアニメーション向けのクリーンなオールクワッドメッシュに変換します。resolutionは密度の指定方法を選びます：quad_count（絶対的なtarget_quads、デフォルト）、quad_area（クワッドあたりのtarget_area）、tolerance、または相対／絶対のスケール。adaptivity（+curvature_weight）は曲率にクワッドを集中させ、少ないクワッドでもシルエットがくっきり保たれるようにします。feature_boundariesはクワッドの流れをハードエッジに整列させます。decimation_levelは密なスキャンでの速度のために入力を事前にデシメートします。 | `input` (+9 optional) |
| `gameres` | SideFX Labs GameRes — 高解像度メッシュ（`input`、input 0）を、polyreduce／Instant Meshes／ボクセルリメッシュを介してゲーム解像度のLODへ縮約します。クックされたSOP出力がその縮約メッシュそのものです。finalcountはポリゴンバジェットを目標にします。use_instantmeshesはクワッドリメッシュに切り替えます。enable_voxelization+resolutionはボクセル再構築を行います。 | `input` (+19 optional) |
| `instant_meshes` | SideFX Labs Instant Meshes — コンパイル済みのInstant Meshesコアを介した、入力メッシュのフィールド整列クワッド／トライのREMESH（外部実行ファイルは起動されません。データ専用のクック）。 | `input` (+6 optional) |
| `polydoctor` | 非多様体／不正なポリゴンを診断・修復します（PolyDoctor） — ブール前／VDB前／シミュレーション前のメッシュ清浄化ツールです。 | `input` (+7 optional) |
| `polyfill` | 境界の穴（LIDAR／スキャンの欠損、ブールの隙間）をパッチポリゴンで埋めます（PolyFill）。fillmodeはパッチのトポロジーを選びます：tris / trifan / quadfan / quads / gridquads（クワッドのグリッド、後のサブディビジョンに最適）または none（穴をグループ化するだけ）。smooth（+smooth_strength、最大50）は新しいパッチをリラックスさせて周囲のサーフェスに馴染ませます。tangent_strengthはパッチが境界の接線にどれだけ強く従うかを制御します（0..2、デフォルト0.4）。patch_groupは作成したパッチポリゴンに後の選択用のタグを付けます。 | `input` (+7 optional) |
| `mesh_repair` | opで多重化されたSideFX Labsの修復ツールキット。repair（Labs Repair）：穴を塞ぐ＋非多様体ジオメトリを修正 — fillmodeが穴パッチのトポロジー（tris..gridquads）を選び、iterations = 修復のパス数。delete_small_parts：切り離された不要なシェルを除去 — mode perimeter\|area、thresholdは相対サイズのカット、extract_largestは最大の単一ピースのみを残します（ノイズからスキャンされたオブジェクトを分離するのに最適）。clean_seams：UVアイランドの継ぎ目エッジを溶かします。fast_remesh（Labs Fast Remesh）：GPU風の均一な再三角形化 — target_polycountが出力サイズを設定し、iterations = リメッシュのパス数。 | `input` (+8 optional) |
| `clean` | Clean SOP — 汚れた／スキャンジオメトリのパラメトリックなクリーンアップ（polydoctor/mesh_repairを補完する、トグル駆動の対応版）。 | `input` (+14 optional) |
| `point_normals` | 生のポイントクラウド（LIDAR／フォトグラメトリのスキャン）に対して、各点の近傍を平面フィッティング（共分散／PCA）して点ごとの面法線を推定します — スキャンには法線がないため、メッシュ化（Poisson／VDB）や壁対床のセグメンテーションの前に必要です。radius_m = 近傍探索半径（メートル）。maxptsは点ごとの近傍数（コスト）を制限します。 | `input` (+3 optional) |
| `segment_planar` | ポイントクラウドの点を、その法線v@Nから垂直なWALL対水平なFLOOR/CEILINGに分類／セグメント化します（先にpoint_normalsを実行）— 建物／室内スキャンの構造抽出。kwall/coshorizは\|N.y\|のしきい値です（0付近 = 壁、1付近 = 水平）。 | `input` (+3 optional) |
| `despeckle` | radius内の近傍がmin_nbrs未満である孤立した外れ点／迷子の点を削除して、ポイントクラウドをデノイズします — メッシュ化の前にスキャナーのノイズ／スペックル／フライヤーを除去します。radius = 近傍探索距離。min_nbrs = 保持のしきい値。 | `input` (+3 optional) |
| `level` | 傾いたポイントクラウドやスキャンを重力に合わせて／まっすぐに整え、地面が平らで水平になるようにします：支配的な地面平面をRANSACフィットし、その法線をPCAで精緻化し、クラウド全体を回転させてその法線が+Y（上）を向くようにします。入力の後にlevel xformを付加して行います。threshold = RANSACのインライア距離。 | `input` (+1 optional) |

### インスタンスとスキャッター

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `scatter_copy` | ワンショットのスキャッター・アンド・インスタンス：ターゲットサーフェス全体に`count`個の点をランダムにスキャッターし、すべての点にソースシェイプをコピー／インスタンスします（植生、岩、氷塊、デブリ、グリーブル）。 | `name` (+6 optional) |
| `instance_attributes` | SideFX Labs Instance Attributes — インスタンサーが読み取る点アトリビュート（`instanceattrib`のアセットパスアトリビュート＋点ごとのpscale/scale/orient）を、入力の点（`input`、input 0）へ書き込み、下流のコピー／インスタンスがシーンを飾れるようにします。 | `input` (+20 optional) |
| `physics_painter` | SideFX Labs Physics Painter — 入力サーフェス（`input`、input 0）全体にオブジェクトをスキャッターし、短いBulletソルブで落ち着かせて自然に静止させます（斜面の上の岩、棚の上の小物）。 | `input` (+19 optional) |
| `copy_to_points` | ソースSOPジオメトリを、ターゲットSOPのすべての点へコピー／インスタンスします（Copy to Points 2.0） — 植生、岩、デブリ、グリーブル、群衆のための中核的なインスタンシングオペレーションです。 | `source`, `target` (+5 optional) |
| `scatter` | 入力ジオメトリのサーフェス全体に`count`個の点をランダムにスキャッター／分布させます（Scatter 2.0） — その後（copy_to_pointsで）インスタンスをコピーする点集合、またはサンプル位置として使います。countは合計の点数。density_attribは点floatアトリビュートによって点の着地場所をバイアスします（ハイトフィールドマスク／オクルージョン／スロープ）。relax_iterationsは点をほぼ均一なポアソンディスク間隔に広げます（塊を除去）。seedは並びをシャッフルします。 | `input` (+6 optional) |
| `pack` | 入力ジオメトリをパックドプリミティブに畳み込みます — 一括でのコピー／インスタンス／変換がはるかに安価な、ジオメトリへの軽量なフラットメモリ参照です（各パックドプリミティブは、移動／回転／スケールできる1つの点のように振る舞います）。pack_by_nameは一意な`name`アトリビュート値ごとに1つのパックドプリミティブを作ります（フラクチャー／ラベル付きジオメトリのピースごとのパッキング）。viewportlodはパックドプリミティブがビューポートでどう描画されるか（full/points/box/centroid/hidden）を制御します — box/pointsに落とせば膨大なインスタンス数でもインタラクティブに保てます。 | `input` (+4 optional) |
| `unpack` | パックドプリミティブを生の編集可能なジオメトリへ展開し直します（packの逆） — パックドインスタンスの基となる点やポリゴンを編集／変形できるようにする前に必要です。 | `input` (+2 optional) |
| `instance` | Instance SOP：各入力点をタグ付けし、レンダー／展開時にジオメトリのインスタンスされたコピーへ展開されるようにします — レンダーされるまで安価なままの、遅延された点インスタンシング。instance_attribは点ごとにインスタンスするSOP／ジオメトリのパスを保持するstring点アトリビュートを指定します（異種インスタンシング）。packは展開されたインスタンスをパックドプリミティブとして出力します。 | `input` (+3 optional) |
| `biome_scatter` | Labs Biome Plant Scatter SOPを介して、入力地形全体に植生／植物をスキャッターします — 密度と間隔の制御を伴うエコシステム／植生のドレッシング（草、低木、樹木）。densityは植物の数を乗じ、spacingは植物間の最小間隔を設定し、seedは並びをシャッフルします。 | `input` (+4 optional) |
| `tag_radial` | 球（中心＋半径）の内側にあるすべての点に i@tag = 1 を書き込んで選択／タグ付けします — ポイントクラウドの一部を分離またはマスクするための球状領域選択。center = 球の中心[x,y,z]。 | `input` (+3 optional) |
| `point_replicate` | 各入力点を、その周囲のシェイプ内に広がる`count`個の新しいジッター付き点へ複製／増殖させます（Point Replicate SOP） — 疎な点を、スプレー／ミスト／ダストのエミッションやシェイプ内スキャッター向けのより充実したクラウドに変えます。count = 入力点ごとの複製数。shape（box/sphere/cylinder/cone/grid/circle/line）+ sizeが広がりのボリュームを設定し、noiseが追加の位置ジッターを加え、copy_attribsはソース点のアトリビュート（Cd、pscale、id...）をその複製に引き継ぎ、attribstocopyがどれを引き継ぐかを指定します。 | `input` (+8 optional) |

### VDBとボリューム

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `vdb_transform_properties` | SideFX Labs VDB Transform Properties — ベクトルVDBの値を、そのボリューム自身のトランスフォームのもとで再導出します。 | `input` (+4 optional) |
| `volume_texture` | SideFX Labs Volume Texture — 入力のボリューム／VDB（`input`、input 0）を、リアルタイムのボリュームテクスチャシェーダー向けにスライスされたフリップブックアトラスへ平坦化します。クックされたSOP出力はスライスプレビューのジオメトリです。modeはパッキングを選び、customfieldはボリュームフィールドを指定し、slices/frameresolutionはアトラスのレイアウトを設定し、equalizedensity/invertdensityは密度を調整します。 | `input` (+12 optional) |
| `vdb_from_particles` | 点／パーティクル → VDB。op=particlesはSDF/fog/mask/velocityのグリッドを構築します（vdbfromparticles）。op=fluidはFLIPパーティクルをフルイド密度のVDBへサーフェス化します（vdbfromparticlefluid）。 | `input` (+26 optional) |
| `vdb_from_polygons` | ポリゴン → VDB SDFおよび/またはfog（往復のメッシュ化／コリジョン／大気表現）。ナローバンド制御と任意の点アトリビュート転送付き。 | `input` (+16 optional) |
| `vdb_convert` | VDBの変換（往復のハブ）：ポリゴン／polysoup／vdb／ネイティブボリューム、SDF↔fogの再分類、精度／型の変更、iso制御、アトリビュート転送、フィーチャーのシャープニング。 | `input` (+15 optional) |
| `vdb_filter` | VDB／ネイティブボリュームに対する単一入力のフィールドフィルタ（smooth、reshape、renormalize、blur、extrapolate）。 | `input` (+29 optional) |
| `volume_combine` | 1つの入力に載った名前付きVOLUMEフィールドを、演算で結合します（volumecombine） — 名前でマッチした dest = op(dest, source)：2つの密度フィールドを加算する、マスクをtemperatureに乗算する、2つの煙シミュレーションのmaxを取る。 | `input` (+12 optional) |
| `volume_rasterize_attributes` | 点のアトリビュートを名前付きのfog VOLUMEへラスタライズします（volumerasterizeattributes） — density/temperature/v/Cdを載せたポイントクラウドを、1つのノードで対応するボリュームFIELDへ変えます（pyro/smokeのソース、または点シミュレーションをレンダー可能なボリュームへベイク）。 | `input` (+14 optional) |
| `volume_rasterize` | 点／パーティクルを密度／アトリビュートのfogボリュームへラスタライズします（点→密度クラウド／pyroソース）。input=ベースボリューム（input0、解像度を定義）。ソースの点／パーティクルはinput1へ配線します。 | `input` (+34 optional) |
| `convert_volume` | ネイティブボリュームのレーン：mode=isooffset（isooffset経由でポリゴン→ネイティブHoudiniボリューム／SDF／テトラ）、tovdb/topoly（totypeへ変換）、またはconvert（汎用）。 | `input` (+12 optional) |
| `vdb_analysis` | VDBに対するフィールド微積分（VDB Analysis SOP）、VEXなし：gradient/curvature/laplacian/closest-point/divergence/curl/length/normalize。 | `input` (+7 optional) |
| `vdb_topology` | opによるアクティブボクセル集合（トポロジー）のオペレーション：activate（vdbactivate）、clip（vdbclip）、resample（vdbresample）、segment（vdbsegmentbyconnectivity）。 | `input` (+23 optional) |
| `vdb_combine` | VDBに対する2入力のCSG／フィールド演算（Volume VOPへの型付きの答え、VEXなし）、op別：sdf（vdbcombine）、fog（volumemix）、vectormerge（vdbvectormerge）、vectorsplit（vdbvectorsplit）。input=A（input0）、input_b=B（input1）。 | `input` (+17 optional) |
| `vdb_advect` | VDBを速度VDB（input1）で輸送します、VEXなし：op=points（vdbadvectpoints）、sdf（vdbadvectsdf）、morph（input1上のターゲットSDFへ向かうvdbmorphsdf）。 | `input` (+23 optional) |
| `vdb_shatter` | SDF VDB → 離散的なピース／球プロキシ、VEXなし：op=fracture（vdbfracture；カッタージオメトリはinput1；sim_rbdへ供給）、spheres（vdbtospheres；RBDプロキシパック）。 | `input` (+24 optional) |
| `volume_visualize` | fogボリュームをビューポートで検査／提示します（レンダーなし）、VEXなし：op=shade（volumevisualizationの密度／emissionシェーディング）、slice（volumesliceの2D断面）。 | `input` (+20 optional) |
| `vdb_reshape` | サーフェスをオフセットしてSDF VDBをリシェイプします（VDB Reshape SDF）：dilate（拡大）、erode（縮小）、open（erode→dilate — 細いスパイクを除去）、close（dilate→erode — ピンホール／亀裂を埋める）。 | `input` (+6 optional) |

### ソルバとシミュレーション

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `rbd_guide` | ガイドジオメトリSOPを、既存のrbdbulletsolverのGuide Sim入力（インデックス4）へ配線し、ガイド付き／アートディレクションされたRBDシミュレーションにします（ソルバのguide_*パラメータがブレンドを駆動）。 | `solver`, `guide` (+1 optional) |
| `rbd_attach_constraints` | オーサリングされた拘束ネットワーク（glue_cluster / rbd_constraints / set_constraint_field）を、既存のrbdbulletsolverのConstraint入力（インデックス1）へ供給します — ライブのsim_rbdソルバに拘束をアタッチします。 | `solver`, `constraints` (+2 optional) |
| `flowmap` | SideFX Labs Flowmap — UV付きサーフェス（`input`、input 0）上に点ごとのフローベクトルアトリビュートをオーサリングし、フローマップによるマテリアルの歪み（川、溶岩）を駆動します。 | `input` (+3 optional) |
| `flowmap_guide` | SideFX Labs Flowmap Guide — サーフェスのフローマップを、手描きのガイドカーブへ向けて操舵します。 | `input` (+7 optional) |
| `flowmap_obstacle` | SideFX Labs Flowmap Obstacle — サーフェスのフローマップを障害物ジオメトリの周りで偏向させます。 | `input` (+6 optional) |
| `flowmap_to_color` | SideFX Labs Flowmap To Color — フローベクトルアトリビュートを、エンジンがフローマップとして読み取るRG(B)カラーへベイクします。 | `input` (+3 optional) |
| `flowmap_visualize` | SideFX Labs Flowmap Visualize — `input`（input 0）に歪みをアニメーションさせてフローマップをプレビューします。 | `input` (+7 optional) |
| `kelvin_wakes_deformer` | SideFX Labs Kelvin Wakes Deformer — 移動するオブジェクトの後を引く、物理ベースのKelvin航跡パターンで水面を変形します。 | `input` (+15 optional) |
| `splatter` | SideFX Labs Splatter — パーティクルフルイド（ペイント／血しぶき）を放出する新規の/obj geoを構築する、自己完結型のSPHフルイド・スプラッターSOURCEです。 | `name` (+15 optional) |
| `procedural_smoke` | SideFX Labs Procedural Smoke — 層状ノイズで駆動される完全プロシージャルな煙のDENSITYボリューム（シミュレーションなし）を保持する、新規の/obj geoを構築します。 | `name` (+9 optional) |
| `volume_adjust_look` | SideFX Labs Volume Adjust Look — 煙／pyroボリュームのLOOK（density / shadow / diffuse / emissionの乗数、任意でグレースケール）をアートディレクションします。 | `input` (+12 optional) |
| `destruction_cleanup` | SideFX Labs Destruction Cleanup — RBD／フラクチャーシミュレーションの出力を後処理します：内面を除去し、法線をカスプ化し、ピース名を再生成し、ピースをチャンクへ最適化します。 | `input` (+11 optional) |
| `rbd_edge_strip` | SideFX Labs RBD Edge Strip — RBDピースのフラクチャー継ぎ目に沿って薄いエッジストリップを抽出します（エッジの欠け／ディテール付け向け）。 | `input` (+4 optional) |
| `loop_volume` | SideFX Labs Loop Volume — ボリューム（smoke/pyro）シーケンスをクロスフェードしてシームレスループにします。 | `input` (+5 optional) |
| `make_loop` | SideFX Labs Make Loop — アニメーションシーケンスをシームレスループに変えます（ジオメトリ、ボリューム、パーティクル）。 | `input` (+14 optional) |
| `lightning` | SideFX Labs Lightning — モデルをまたぐプロシージャルな稲妻／アークのジオメトリを生成します。 | `input` (+16 optional) |
| `rbd_solver` | すでにフラクチャーされたピース＋任意の拘束ネットワーク向けの素のBulletソルバ — グラニュラーフラクチャーのレーン（rbd_voronoi/vdb_shatter/rbd_constraints/set_constraint_field）を、（sim_rbd/rbd_destructionと違って）再フラクチャーなしで実際にSIMULATEできるようにするミッシングリンクです。pieces = パックドフラクチャーSOP（Geometry in0）。constraints = 任意の拘束ネットSOP（in1）。collider = 任意のメッシュ／ハイトフィールド（in3）。 | `pieces` (+50 optional) |
| `sim_rbd` | 剛体破壊（SOP Bulletレーン）：source -> rbdmaterialfracture::3.0 -> rbdbulletsolver。 | `name` (+81 optional) |
| `rbd_constraint_properties` | ソルバのglueネットワーク上のRBD拘束のPHYSICS（破断のダイヤル）を、rbdconstraintproperties::2.0でオーサリングします。 | `solver` (+18 optional) |
| `rbd_material_fracture` | ソルバなしで、MATERIAL TYPEでジオメトリを事前フラクチャーします（rbdmaterialfracture::3.0） — concrete \| glass \| wood \| customのプリセット。 | `input` (+31 optional) |
| `rbd_voronoi` | アートディレクション制御のための素のボロノイフラクチャー（voronoifracture::2.0）：source -> セルをスキャッター -> フラクチャー（マテリアルプリセットなし）。 | `name` (+18 optional) |
| `rbd_interior` | フラクチャーされたジオメトリの内面ディテール（rbdinteriordetail SOP）：'inside'の亀裂面をノイズで変位させ、割れたコンクリート／岩が平らな切断面ではなく本物の内部として見えるようにします。 | `input` (+18 optional) |
| `rbd_constraints` | フラクチャーされたピースから拘束のNETWORK GEOMETRY（ボンドグラフ）を構築します：method=rules（rbdconstraintsfromrules）またはmethod=adjacency（connectadjacentpieces）。 | `input` (+13 optional) |
| `rbd_configure` | フラクチャーされたピースのピースごとのダイナミクス＋アクティベーション（rbdconfigure SOP）：active/animated、density/bounce/friction、minactivationimpulse（衝撃トリガー）、overlap、type/pintypeのプリセット、visualize。 | `input` (+14 optional) |
| `rbd_collision` | TERRAIN BRIDGE：メッシュ／ハイトフィールドのコライダーを、既存のrbdbulletsolverのCollision Geometry入力（インデックス3）へ配線し、デブリが実際にキャプチャした地形の上に落ち着くようにします。 | `solver`, `collider` (+10 optional) |
| `rbd_force` | 重力／ドラッグを超えたRBDデブリ向けの型付きDOP力（VEXなし）：wind/uniform/point/vortex/fan/drag/explosion（explosion\|blast -> popaxisforceの放射状衝撃波）。 | 12 optional |
| `rbd_cache` | RBDシミュレーションの後に、制限された明示的な書き込みパスで、File Cache 2.0 SOPを構築します（書き込みは決して行いません）。 | `input`, `file` (+7 optional) |
| `rbd_exploded` | デバッグ／検査：フラクチャーされたピースを離して広げ、割れを確認します（rbdexplodedview SOP）。 | `input` (+6 optional) |
| `rbd_destruction` | TERRAIN DESTRUCTIONのマクロ：再構築されたアセットをフラクチャーし、実際にキャプチャした地形の上へエンドツーエンドで崩落させます。building -> rbdmaterialfracture（+glue）-> [rbdconstraintproperties] -> DEMをコリジョンとして配線したrbdbulletsolver。 | `name` (+20 optional) |
| `sim_flip` | FLIP液体（深いコンテナ＋ソルバ）：ソースプリミティブ（デフォルトのbox、またはあなたの`source_geo`）が供給するflipcontainer + flipsolverを構築し、source->Sources(0)/container->Container(1)に配線します。 | `name` (+44 optional) |
| `flip_collision` | ジオメトリ → FLIPコリジョンボリューム（Collision Source 2.0 SOP）。 | `input` (+16 optional) |
| `flip_flood` | 地形の氾濫マクロ：1回の呼び出しで、DEM/ハイトフィールドSOP（`input`）-> convertheightfield -> collisionsourceのコライダー -> 自動サイズのflipcontainer（DEMのbbox＋パディング＋ヘッドルームにフィット）-> flipsolverを構成し、コライダーをソルバのCollisions入力へ自動配線します。 | `name`, `input` (+22 optional) |
| `flip_source` | ジオメトリ → FLIPパーティクル（Flip Source SOP）：初期充填および/または連続放出。flipsolverのSources入力へ供給します。 | `input` (+15 optional) |
| `flip_boundary` | FLIPコンテナ向けの開放境界のソース／シンク（Flip Boundary SOP）：none/velocity/pressure/hydro_pressureの境界タイプ（hydro = 沿岸／氾濫の水際線）。 | `input` (+11 optional) |
| `flip_tank` | 事前充填されたFLIPパーティクルのプール（Particle Fluid Tank SOP）：最初から満杯で始まるプール／港／貯水池。 | `name` (+11 optional) |
| `flip_force` | FLIP/DOPシミュレーション向けの型付き力ノード（VEXなし）：ftype -> uniformforce/vortexforce/windforce/drag/pointforce/fan/popaxisforce。 | 13 optional |
| `sim_pop` | POPパーティクル（マスター）：SOPのdopnet（input0=エミットgeo）がpopobject -> popsolver::2.0をラップし、ソースはSources入力（usecontextgeo='first'の修正）、デフォルトのpopforce重力がPre-Solveにチェーンされます。 | `name` (+38 optional) |
| `pop_source` | 型付きのパーティクルエミッター（popsource::2.0）を既存のPOP dopnetへ追加し、popsolverのSources入力へ配線します。 | `dopnet` (+23 optional) |
| `pop_force` | 1つの型付きPOP力をPOP dopnetへ追加し、popsolverのPre-Solve入力へチェーンします（力はチェーンし、きれいにスタックします）。 | `dopnet` (+54 optional) |
| `pop_import` | シミュレーションされたPOPパーティクルを、dopimport::2.0を介してdopnetからSOPへ引き戻します（データ専用のインポーター。dopioのプリセットメニューはヘッドレスでは populate されません）。 | `dopnet` (+7 optional) |
| `pop_collision` | POP dopnet内で、SOP/地形のコライダーに対してパーティクルをコリジョンさせ（popcollisiondetect）、Pre-Solveへチェーンします。 | `dopnet` (+15 optional) |
| `pop_group` | POP dopnetのPre-Solveへチェーンされる、型付きルール（VEXなし）によるパーティクルストリームのグループ化または分割。op=group -> popgroup（groupnameへタグ付け；型付きの境界領域＋ランダムな部分集合＋ブール結合）。op=stream -> popstream（同じ型付きルールで名前付きサブストリームを分割）。 | `dopnet` (+30 optional) |
| `pop_kill` | POP dopnetのPre-Solveへチェーンされる、型付きルール（VEXなし）によるパーティクルのkill／制限／クランプ。op=kill -> popkill（型付きの境界領域＋ランダムな部分集合）。op=limit -> poplimit（ハードなドメインボックス；clamp/bounce/wrap）。op=softlimit -> popsoftlimit（ソフトな押し戻し領域）。op=speedlimit -> popspeedlimit（speed/spinをクランプ）。enablerule/randomcodeは決して設定されません。 | `dopnet` (+36 optional) |
| `pop_property` | POP dopnetのPre-Solveへチェーンされる、型付きのPOPプロパティノード（VEXなし）でパーティクルごとのアトリビュートを整形します。op=physical -> popproperty（pscale/mass/bounce/friction/drag/cling）。op=color -> popcolor（constant/random/ramp/blendのCd＋alpha）。op=sprite -> popsprite（カメラカード）。op=velocity -> popvelocity。op=lookat/torque -> orient。 | `dopnet` (+39 optional) |
| `pop_instance` | POP dopnet向けのインスタンシング／レンダー受け渡し（VEXなし）。op=instance -> popinstance（instancepathを書き込み、点がレンダー時にSOPをインスタンスするようにする；Pre-Solveへチェーン）。op=replicate -> popreplicate（二次的なスプレー向けに親ごとに子を発生させる；Sources入力へ配線）。 | `dopnet` (+26 optional) |
| `pop_cache` | シミュレーションされたパーティクルをディスクへキャッシュするため、pop_importノードの後にFile Cache 2.0 SOPを構築します（書き込みは決して行いません）。 | 12 optional |
| `pop_flock` | POP dopnet向けのボイド／ステアリング（VEXなし）。1つの挙動ノードをPre-Solveへチェーンします。behaviorはpopflock/popinteract/popsteer{seek,avoid,wander,separate,cohesion,align,obstacle}/popproximityを選びます。popsteercustom（VEX）は除外され、すべてのuselocal*フィールド（wanderのノイズプリセットを含む）はデフォルトのままです。 | `dopnet`, `behavior` (+43 optional) |
| `pop_scatter_sim` | 地形／スキャンのパーティクルスキャッターのマクロ（flip_floodの類似物）：1回の呼び出しでPOPレーン全体を新規の/obj geoへ構成します — エミットgeo -> dopnet(popobject+popsource) -> popsolver + 型付きの力プリセット -> 地形／スキャンのコライダーに対する任意のpop_collision -> SOPへ戻すdopimport -> 任意のcopy_to_pointsによるレンダー受け渡し。 | `name` (+14 optional) |
| `sim_pyro` | Pyro（炎／煙）：モダンなSOPレーンへ移行済み pyrosource -> SOP pyrosolver（自己境界のコンテナ）+ 任意のcollisionsource::2.0コライダー。 | `name` (+75 optional) |
| `pyro_source` | Pyroのエミッションソース（pyrosource SOP）：geo/点をソースフィールド（density/temperature/fuel/burn/vel）へラスタライズし、pyrosolverのSources入力へ供給します。 | `input` (+10 optional) |
| `pyro_collision` | ジオメトリ／地形 → pyroコリジョンボリューム（Collision Source 2.0 SOP）：シーンコリジョンのブリッジ。pyrosolverのCollision入力へ供給し、煙がDEM、建物、RBDデブリで偏向するようにします。 | `input` (+10 optional) |
| `pyro_ground` | 地面／野火のマクロ：DEMハイトフィールド -> コライダー + エミッション領域上のpyrosource -> SOP pyrosolver（タイプ別＋風に合わせて調整）-> volumevisualization。 | `name`, `input` (+22 optional) |
| `pyro_burst` | Pyroの爆発／火球ソース（pyroburstsource SOP）：入力点を、explosion/shockwave/muzzle/ringのシェル＋後を引くembersへ変え、pyrosolverのSources入力へ供給します。 | `input` (+25 optional) |
| `pyro_explosion` | 爆発のマクロ：中心の単一バースト点 -> pyroburstsource（explosion + embers）-> SOP pyrosolver（熱い火球）-> volumevisualization。 | `name` (+30 optional) |
| `pyro_visualize` | pyro/ボリュームフィールドのビューポートルック（volumevisualization SOP）：安価なビューポートシェーディングのみ、レンダーではありません。 | `input` (+14 optional) |
| `pyro_shade` | pyroボリュームのレンダー対応シェーディングフィールド（pyrobakevolume SOP）：Karmaのレンダー準備ノード。smoke/fire/scatterのルックをベイクし、Pyroマテリアルを割り当てます。 | `input` (+25 optional) |
| `pyro_post` | pyroシミュレーションのエクスポート／レンダー準備（pyropostprocess::2.0 SOP）：フィールドのmin/max（Karmaが必要とする）を計算し、任意で.vdbシーケンス向けのネイティブ→VDB変換を行います。 | `input` (+11 optional) |
| `pyro_cache` | pyroシミュレーションの後に、制限された明示的な書き込みパス＋bgeo/vdbのファイルタイプで、File Cache 2.0 SOPを構築します（書き込みは決して行いません）。 | `input`, `file` (+7 optional) |
| `whitewater_source` | ホワイトウォーターのエミッションソース（Whitewater Source 3.0 SOP）：FLIP液体シミュレーションから、foam/spray/bubblesがどこで生まれるかを決めるエミッションマスク。 | `input` (+21 optional) |
| `sim_whitewater` | ホワイトウォーター（foam/spray/bubble）：モダンなSOPレーンへ移行済み whitewatersource::3.0 -> whitewatersolver（SOP）-> 任意のpost。 | 39 optional |
| `whitewater_post` | ホワイトウォーターの後処理（Whitewater Post Process SOP）：解かれたfoam/spray/bubbleをレンダー向けに整形します — density/pscaleのramp、particles/fog/meshの出力、コンテナのクリップ。 | `input` (+17 optional) |
| `fluid_surface` | FLIPパーティクルをフルイドサーフェスへメッシュ化します（Particle Fluid Surface 3.0 SOP）。 | `input` (+19 optional) |
| `flip_volume_combine` | 低解像度のFLIPシミュレーションのフィールドを、高解像度のディテールと結合してUP-RESSINGします（flipvolumecombine） — H20のup-resワークフロー：低解像度で安価にシミュレーションし、重要な箇所にのみ高周波のサーフェス／速度ディテールをブレンドします。input=低解像度フィールド（in0）；high_res=高解像度フィールド（in1）；container=高解像度の参照コンテナ（in2）；clip_bbox=クリッピングボックス（in3）、すべてネットワークをまたいで自動ブリッジされます。 | `input` (+14 optional) |
| `flip_cache` | シミュレーションの後に、制限された明示的な書き込みパスで、File Cache 2.0 SOPを構築します（書き込みは決して行いません）。 | `input`, `file` (+6 optional) |
| `sim_ripple` | Ripple Solver SOPによる、グリッド上の安価な表面波（レストジオメトリはinput 0）。 | `name` (+8 optional) |
| `sim_grains` | グラニュラーPBD（砂／雪／湿った砂／デブリ）：SOPのdopnet（input0=エミットgeo）がpopobject -> popsolver::2.0をラップし、popgrainsのPBDソルバがソルバの'Solvers to be attached'入力を介してアタッチされ、デフォルトの重力popforce付き。 | `name` (+35 optional) |
| `set_constraint_field` | RBD（剛体破壊）拘束ネットワークのアトリビュートを、グループ単位で、attribcreate::2.0を介した型付きのLITERAL値として設定／オーサリング／命名／破断します — フラクチャー上のglue/hard/softボンドを制御する、データ専用でVEXゼロ／ラングルゼロの手段です：constraint_name（ソルバがマップする関係タイプ — Glue/Hard/Softまたはカスタム名）、next_constraint_name（ボンドが破断したときに何になるか）、strength（破断のしきい値）、restlength（soft/springのレスト長）、broken（事前破断フラグ0\|1）。 | `input` (+8 optional) |
| `glue_cluster` | フラクチャーされたRBDピースをチャンク／クラスター化し、構造がシャードごとではなくCHUNKやスラブ単位で割れるようにします（gluecluster SOP） — 建物／壁がまとまったセクションで崩れる、破壊のアートディレクションで最もよく使われる制御です。 | `input` (+14 optional) |
| `rbd_constraints_from_curves` | ユーザーカーブに沿ってRBD（剛体破壊）拘束ネットワークを構築／ルーティングします（rbdconstraintsfromcurves SOP） — 鉄筋、ケーブル、鎖、ステッチ、手描きの破断線のためのカスタムなボンドルーティング。そしてSOPで到達可能なHINGE（機械的）接続タイプ。 | `input`, `curves` (+11 optional) |
| `rbd_constraints_from_lines` | 明示的なLINE SEGMENTSからRBD（剛体破壊）拘束ネットワークを構築します（rbdconstraintsfromlines SOP） — インタラクティブなハンドル描画のラインツールのデータ専用版：リテラルな点ペアとして与えられた各ラインが、それが横切るフラクチャーピースの間にボンドをルーティングします。 | `input`, `lines` (+13 optional) |
| `rbd_group_constraints` | RBD（剛体破壊）拘束ネットワークに名前を付け／グループ化し／整理して、ターゲット可能な名前付きプリミティブグループにします（rbdgroupconstraints SOP）。ソルバ、set_constraint_field、rbd_constraint_propertiesがそれらのボンドを選択できるようにします。 | `input`, `constraints` (+6 optional) |
| `voronoi_adjacency` | ボロノイフラクチャーから、ピースのADJACENCYグラフ／ボンドトポロジー（どのフラクチャーピースがどれに接するか）を構築します（voronoiadjacency SOP） — RBD（剛体破壊）拘束ネットワークがそれに沿ってルーティングされる隣接ポリラインです。 | `input` (+1 optional) |
| `sim_viscosity` | 粘性FLIPのスキャフォールド（シャーベット／融雪水／蜂蜜／溶岩）：粘性力を有効にしたflipcontainer + flipsolver。 | `name` (+11 optional) |
| `ocean_surface` | 平坦なスペクトルの大水面OCEAN／SEAサーフェス — オーシャンスペクトルで変位（Ocean Evaluate 2.0）させてうねる波にしたグリッド。 | `name` (+7 optional) |
| `ocean_spectrum` | 完全なオーシャン波SPECTRUM（Ocean Spectrum）をオーサリング＋大きなグリッドへ評価します — ocean_surfaceが届かない深い'ルック'の制御：スペクトルモデル、水深、うねり、フェッチ、風向／バイアス、決定論的なシード＋シームレスループ。 | `name` (+29 optional) |
| `ocean_evaluate` | 任意のジオメトリをオーシャンSPECTRUMで変形します（SOPレベルのOcean Evaluate）。 | `input`, `spectrum` (+9 optional) |
| `ocean_foam` | オーシャンサーフェスのカスプからFOAM／ホワイトウォーター／スプレーの点を生成します（Ocean Foam SOP） — 砕ける波頭の海泡レイヤー。 | `input` (+17 optional) |
| `ocean_source` | オーシャンスペクトルをFLIPフルイドタンクへカップリングします（Ocean Source 2.0） — スペクトルオーシャンから、飛沫の上がる水／砕ける波のFLIPシミュレーションをシードするスキャフォールド。particlesep = FLIPパーティクルの分離；waterlevel = レストの海面レベル。 | `name` (+4 optional) |
| `point_velocity` | 点の速度アトリビュートvをオーサリングします（Point Velocity SOP） — FXのシード速度の主力です。 | `input` (+10 optional) |
| `volume_velocity` | 速度VOLUMEをオーサリングします（Volume Velocity SOP） — pop_force(advect)を介して波頭のスプレー／雪／雨を駆動する、非シミュレーションの'風洞'速度フィールド。input = 書き込み先のボリューム／VDB；任意の点入力はvをラスタライズします。 | `input` (+9 optional) |
| `debris_source` | フラクチャーされた／静的なピースの表面から二次的なDEBRISソースを放出します（Debris Source SOP） — emit-RBDまたはPOPの二次的な'ジュース'シミュレーションへ供給する、フレームごとのエミッションマップ（density/age/distanceアトリビュート）。 | `input` (+7 optional) |
| `cloud` | ボリュームのCLOUDプリミティブ（積雲／空の雲／fogボリュームの密度フィールド）：ソースgeo -> Cloud 2.0（SDF/density/ナローバンド）-> Cloud Noise（billowy/wispyの変位）-> 任意のCloud Adjust Density Profile（ベース／かなとこの整形）。 | `name` (+25 optional) |
| `cloud_shape` | H20+のCloud Shapeツールセット（cloudshapegenerate）で、モダンでアートディレクション可能な雲を生成します — 非推奨となった一枚岩の`cloud`の置き換えです。 | `name` (+18 optional) |
| `cloud_billowy_noise` | 雲の密度VDB上の、もくもくとしたカリフラワー状の変位（cloudbillowynoise） — モダンな高ディテールの積雲モディファイア。 | `input` (+16 optional) |
| `cloud_wispy_noise` | 雲の密度VDB上の、かすんだ／筋状の速度移流された変位（cloudwispynoise） — 巻雲、引き伸ばされたかなとこ、風に吹かれたすじ。 | `input` (+11 optional) |
| `cloud_clip` | 平面＋任意のノイズで雲の密度VDBをクリップ／カットします（cloudclip） — 平らな積雲のベース、剪断されたかなとこ、切り取られた頂部。 | `input` (+11 optional) |
| `solver` | 汎用のSOPフィードバック／タイムループソルバ — 汎用目的の反復プリミティブ（累積的な侵食、成長、セルオートマトン、あらゆるフレームごとのフィードバック）。DOPのsim_*ファミリーとは別物です。 | `input` (+6 optional) |
| `sim_vellum` | Vellum（XPBD）マスター（SOP）：source -> Vellum Constraints -> Vellum Solver。 | `name` (+65 optional) |
| `vellum_collision` | 外部／地形のコライダーをVellumソルバのCollision Geometry入力（インデックス2）へ配線し、コリジョン応答を調整します。 | `solver`, `collider` (+14 optional) |
| `vellum_attach` | Vellumのクロス／ジオメトリを（動く）RIGへアタッチします — 専用のVellum Attach Constraints SOP。 | `input`, `rig` (+9 optional) |
| `vellum_constraint` | 既存のチェーンに追加のVellum拘束（welds/glue/pins/attach/stitch/struts）を、第2入力の追加を介してレイヤーします。 | `solver` (+36 optional) |
| `vellum_force` | Vellumソルブへの外部力。 | 24 optional |
| `vellum_drape` | レスト状態／プリロールの安定化。 | `solver` (+29 optional) |
| `vellum_source` | 連続的なエミッション／シミュレーション途中での拘束パッチの追加（DOPスコープ、上級 — DOPに降りる唯一のVellumツール）。 | 12 optional |
| `vellum_post` | Vellumシミュレーションのレンダー準備（vellumpostprocess SOP）：ヘアチューブ生成、平滑化（subdivide）、detangle、剛性。 | `input` (+15 optional) |
| `vellum_cache` | Vellumシミュレーションの後にFile Cache 2.0 SOPを構築します（書き込みは決して行いません）。 | `input`, `file` (+8 optional) |
| `sim_mpm` | MPM（Material Point Method）ネットワーク（SOP）：source -> mpmsource -> mpmsolver。 | `name` (+24 optional) |
| `mpm_collider` | MPMシミュレーションに、コリジョン／インタラクトする対象を与えます — コライダーを、既存のmpmsolverのMPM Colliders入力（インデックス1）へ配線します。 | `solver`, `collider` (+11 optional) |
| `mpm_container` | MPMシミュレーションのDOMAINを区切り、そのMASTER解像度を設定します — `mpmcontainer`を、既存のmpmsolverのMPM Container入力（インデックス2）へ配線します。 | `solver` (+9 optional) |
| `mpm_surface` | MPMシミュレーションをRENDERABLEにします — その後に`mpmsurface`を構築して、シミュレーションのパーティクルをメッシュ化／サーフェス化します。 | `input` (+14 optional) |
| `mpm_postfracture` | MPM破壊ショットをシミュレーション→フラクチャーします — MPMシミュレーションが実際にどこで引き伸ばし壊したかで駆動して高解像度ジオメトリをフラクチャーし、亀裂が（事前フラクチャーと違って）実際の変形に追従するようにします。 | `geo`, `particles` (+11 optional) |
| `mpm_deformpieces` | MPMシミュレーションを、事前フラクチャーされた名前付きピースへリターゲットします — 剛体または高解像度のレンダーチャンクを（より安価な）MPMシミュレーションで駆動し、高解像度を直接シミュレーションせずに最終ジオメトリがソルブに合わせて変形／移動するようにします。 | `pieces`, `particles` (+8 optional) |
| `mpm_debrissource` | MPMシミュレーションから二次的なデブリを放出します — 材料が強く引き伸ばされる、速く動く、または表面に近い箇所で、余分なチャンク／パーティクルを発生させます（破壊や衝撃のシミュレーションの上に乗せる、破片／スプレー／火花のパス）。 | `input` (+10 optional) |
| `glue_constraint` | KineFX Glue Constraint Relationship（glueconrel） — 束縛されたオブジェクトを、`strength`を超えるインパルスがボンドを破断するまで接着し、その後破断を伝播させる、DOP拘束関係データノード。 | 10 optional |
| `hard_constraint` | KineFX Hard Constraint Relationship（hardconrel） — 束縛されたオブジェクトをレスト長にピン留めする剛性のDOP関係。任意の角度モーターとソルバ剛性（CFM/ERP）付き。 | 14 optional |
| `no_constraint` | KineFX No Constraint Relationship（noconrel） — 束縛されたオブジェクトを、いかなる拘束力もなしに相互に影響し合う存在にするDOP関係（コリジョンのみ／プレースホルダー）。 | 7 optional |
| `bullet_soft_constraint` | KineFX Bullet Soft Constraint Relationship（bulletsoftconrel） — 線形＋任意の角度の剛性／減衰と、任意の塑性（しきい値を超えた永続的な変形）を備えた、ばね状のBullet関係。 | 18 optional |
| `cone_twist_constraint` | KineFX Cone Twist Constraint Relationship（conetwistconrel） — twist/out/upの回転を円錐内に制限するBulletコーンツイストジョイント。任意のソフトリミットとモーター付き。 | 20 optional |
| `constraint_relationship` | KineFX Constraint Relationship（conrelationship） — 2つの束縛されたオブジェクトがどう関係するかを定義する汎用の関係データノード（タイプ＋2状態の破断／ばねパラメータ）。 | 10 optional |
| `apply_constraint` | KineFX Constraint（constraint） — `affected`と`affector`のシミュレーションオブジェクトの間に、名前付きの拘束関係を適用します（関係をオブジェクトに束縛するDOPノード）。 | 11 optional |
| `constraint_network_relationship` | KineFX Constraint Network Relationship（constraintnetworkrelationship） — 拘束NETWORKに関係を適用します。任意で点アトリビュートによってaffected/affectorオブジェクトをマッチングします。 | 12 optional |
| `motion_data` | KineFX Motion（motion） — オブジェクトの位置／ピボット／回転と線形＋角速度を運ぶDOP Motionデータノード（RBDまたはエージェントオブジェクトの初期状態／ターゲットモーション）。 | 11 optional |
| `softbody_constraint` | KineFX SBD Constraint（sbdconstraint） — オブジェクトの拘束された点を、ゴールのオブジェクト／点／位置へピン留め（`type` 0）またはばねリンク（`type` 1）するソフトボディダイナミクス拘束。任意の力＆長さの制限付き。 | 19 optional |
| `cloth_stitch_constraint` | KineFX Cloth Stitch Constraint（clothstitchconstraint） — クロスオブジェクトの拘束された点を、与えられた剛性＆減衰でゴールのオブジェクト／点へステッチします（`type` 0/1）。 | 11 optional |
| `fem_attach_constraint` | KineFX FEM Attach Constraint（femattachconstraint） — 拘束されたFEMオブジェクトの点を、レストオフセットでゴールオブジェクトへアタッチします。任意の距離しきい値によるフィルタリング付き。 | 13 optional |
| `fem_fuse_constraint` | KineFX FEM Fuse Constraint（femfuseconstraint） — 2つのFEMオブジェクトのマッチした点を（順序付き点グループまたは識別子アトリビュートでマッチ）共有境界へ融合します。 | 12 optional |
| `fem_region_constraint` | KineFX FEM Region Constraint（femregionconstraint） — 2つのFEMオブジェクトの重なり合う四面体領域を一緒に拘束します。任意で識別子アトリビュートによってパーツをマッチングします。 | 10 optional |
| `fem_slide_constraint` | KineFX FEM Slide Constraint（femslideconstraint） — FEMオブジェクトの点を、ゴールオブジェクトの表面に沿ってスライドするよう拘束します（接続モデルはattract/repel）。任意の距離しきい値によるフィルタリング付き。 | 14 optional |
| `fem_target_constraint` | KineFX FEM Target Constraint（femtargetconstraint） — FEMオブジェクトの拘束された点を、与えられた剛性＆減衰でアニメーションされたターゲット位置へソフトに引き寄せます（`type` 0/1）。 | 9 optional |
| `ragdoll_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：キャラクター／スケルトンジオメトリ（input 0）上にKineFXラグドールソルバ（kinefx::ragdollsolver）を構築します。 | `input` (+16 optional) |
| `muscle_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：筋肉ジオメトリ（input 0）上にマッスルソルバ（musclesolver）を構築します。 | `input` (+16 optional) |
| `muscle_solver_fem` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：筋肉ジオメトリ（input 0）上にFEMマッスルソルバ（musclesolverfem）を構築します。 | `input` (+16 optional) |
| `muscle_solver_vellum` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：筋肉ジオメトリ（input 0）上にVellumマッスルソルバ（musclesolvervellum）を構築します。 | `input` (+16 optional) |
| `tissue_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：組織／皮膚ジオメトリ（input 0）上に組織（FEMフレッシュ）ソルバ（tissuesolver）を構築します。 | `input` (+12 optional) |
| `tissue_solver_vellum` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：組織ジオメトリ（input 0）上にVellum組織ソルバ（tissuesolvervellum）を構築します。 | `input` (+15 optional) |
| `skin_solver_vellum` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：皮膚ジオメトリ（input 0）上にVellum皮膚ソルバ（skinsolvervellum）を構築します。 | `input` (+16 optional) |
| `armature_deform` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：キャラクタージオメトリ（input 0）上にアーマチュアデフォームソルバ（armaturedeform）を構築します — 準静的な筋肉／皮膚の変形。 | `input` (+13 optional) |
| `fem_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：新規のdopnet内にFEMソフトボディソルブクラスター（femsolidobject -> femsolver）を構築します。 | `name` (+33 optional) |
| `solid_object_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：新規のdopnet内にsolid/clothのFEMクラスター（solidobject -> femsolver）を構築します。 | `name` (+29 optional) |
| `filament_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：新規のdopnet内にフィラメント／ストランドダイナミクスクラスター（filamentobject -> filamentsolver）を構築します。 | `name` (+19 optional) |
| `crowd_solver` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：新規のdopnet内に群衆／クリーチャーエージェントのソルブクラスター（crowdobject -> crowdsolver::3.0）を構築し、配線されたソース（または初期geoのSOPパス）からエージェントを読み取ります。 | `name` (+39 optional) |
### KineFX

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `character_skeleton` | KineFX Skeleton — スケルトンを作成するためのオーサリングコンテナ（kinefx::skeleton）。 | `skeleton` (+4 optional) |
| `configure_joints` | KineFX Configure Joints — Full Body IK / Ragdoll / Rig Pose 用のソルバー設定アトリビュートをスケルトン（input 0）に書き込みます。 | `skeleton` (+15 optional) |
| `configure_joint_limits` | KineFX Configure Joint Limits — スケルトン（input 0）に回転/移動のジョイント制限とリミットガイド表示を設定します。 | `skeleton` (+14 optional) |
| `orient_joints` | KineFX Orient Joints — スケルトン（input 0）のジョイントの向き（`transform` ポイントアトリビュート）を再計算し、reference/up ベクトルを使って各ジョイントを子に向けます。 | `skeleton` (+10 optional) |
| `parent_joints` | KineFX Parent Joints — スケルトン階層（input 0）内のジョイントの親子関係を組み替えます。 | `skeleton` (+2 optional) |
| `delete_joints` | KineFX Delete Joints — スケルトン（input 0）から `group` で指定したジョイントを削除（または指定分のみ保持）します。オプションで子へ連鎖させます。 | `skeleton` (+5 optional) |
| `group_joints` | KineFX Group Joints — 選択式からスケルトン（input 0）上のジョイントの名前付きポイントグループを作成/更新します。既存グループとのブーリアンマージに対応します。 | `skeleton` (+7 optional) |
| `skeleton_blend` | KineFX Skeleton Blend — 1つ以上のスケルトンのポーズをベーススケルトンにブレンドします。 | `skeleton` (+14 optional) |
| `skeleton_mirror` | KineFX Skeleton Mirror — スケルトン（input 0）のジョイントを平面または点を挟んでミラーリングし、ミラーしたジョイントを find/replace トークンでリネームします（例：`_l` -> `_r`）。 | `skeleton` (+13 optional) |
| `rig_doctor` | KineFX Rig Doctor — スケルトンを検証・修復します。欠落したジョイント名/トランスフォームを初期化し、名前をサニタイズし、input 0 のリグから階層アトリビュート（親インデックス、子インデックス、評価順）を出力します。 | `skeleton` (+16 optional) |
| `visualize_rig` | KineFX Visualize Rig — input 0 のスケルトンからリグ可視化ジオメトリ（ジョイントのグノモン/ボーンリンク、color/scale でスタイル設定）を生成します。 | `skeleton` (+11 optional) |
| `rig_pose` | KineFX Rig Pose — スケルトン（input 0）に対するインタラクティブな FK/IK ポージング SOP です。 | `skeleton` (+16 optional) |
| `compute_rig_pose` | KineFX Compute Rig Pose — スケルトン（input 0）からリグポーズを評価し、結果のトランスフォーム/パラメータアトリビュートをジオメトリにベイクします（rig_pose のヘッドレス版）。 | `skeleton` (+15 optional) |
| `rig_match_pose` | KineFX Rig Match Pose — `skeleton`（input 0、ターゲットリグ）を `source`（input 1、ソースリグ）のポーズに合わせてポージングします。オプションでバウンディングボックスと基準フレームで位置合わせします。 | `skeleton`, `source` (+18 optional) |
| `rig_mirror_pose` | KineFX Rig Mirror Pose — スケルトン（input 0）のアニメーション POSE を対称軸/平面を挟んでミラーリングし、左右のジョイントを名前トークン（例：`_l`<->`_r`）または編集距離で対応付けます。 | `skeleton` (+21 optional) |
| `rig_stash_pose` | KineFX Rig Stash Pose — スケルトン（input 0）の現在のポーズをポイントアトリビュートに保存（`mode`=store）するか、以前スタッシュしたポーズを復元（`mode`=restore）します。 | `skeleton` (+12 optional) |
| `rig_copy_transforms` | KineFX Rig Copy Transforms — `source`（input 1）から `skeleton`（input 0、コピー先リグ）へジョイントトランスフォームをコピーします。ジョイントはマッピングアトリビュートまたはマッチアトリビュートで対応付けます。 | `skeleton`, `source` (+6 optional) |
| `ik_chains` | KineFX IK Chains — `targets`（input 1）として与えたゴール位置に向けて、スケルトン（input 0）の 2 ボーン IK チェーンを解きます。 | `skeleton`, `targets` (+2 optional) |
| `full_body_ik` | KineFX Full Body IK — 設定したエフェクタージョイントがターゲットに到達するよう、`skeleton`（input 0）全体の IK ポーズを解きます。オプションの `targets`（input 1）でゴールジオメトリを与えます。 | `skeleton` (+25 optional) |
| `fbik_configure_targets` | KineFX Full Body IK Configure Targets — FBIK ターゲット設定（ジョイントごとのオフセット、レストポーズ基準、重心ターゲット）をスケルトン（input 0）に書き込みます。オプションの input 1 でターゲットジオメトリを与えます。 | `skeleton` (+13 optional) |
| `spline_ik` | KineFX Spline IK — ジョイントを通してフィットさせたスプラインに沿ってスケルトン（input 0）のジョイントチェーンを駆動し、滑らかなカーブベースの制御（背骨、尻尾、触手）を提供します。 | `skeleton` (+17 optional) |
| `reverse_foot` | KineFX Reverse Foot — スケルトン（input 0）にリバースフットのロールセットアップを構築し、かかと/母指球/つま先のピボットマーカーを追加して足のロールとピボットを可能にします。 | `skeleton` (+8 optional) |
| `stabilize_joint` | KineFX Stabilize Joint — アニメーションスケルトン（input 0）のジョイントのジッターを除去し、フレーム範囲にわたってその位置に固定します。位置/角度の変化制限とブレンドイン/アウトに対応します。 | `skeleton` (+21 optional) |
| `pose_difference` | KineFX Pose Difference — `skeleton`（input 0）のポーズと `reference` ポーズ（input 1）のジョイントごとの差分を計算し、出力アトリビュートに格納します（オプションで位置/回転/スケールのみ、反転、またはオフセットとして適用）。 | `skeleton`, `reference` (+12 optional) |
| `joint_capture_biharmonic` | KineFX Joint Capture Biharmonic (kinefx::jointcapturebiharmonic) — `skeleton`（input 1）を影響リグとして、内部でテトラ化した `geometry`（input 0）上で双調和関数を解くことにより、滑らかな boneCapture スキニングウェイトを計算します。 | `geometry`, `skeleton` (+22 optional) |
| `joint_capture_proximity` | KineFX Joint Capture Proximity (kinefx::jointcaptureproximity) — `skeleton`（input 1）のボーンへの近接に基づいて、`geometry`（input 0）に boneCapture スキニングウェイトを割り当てます。 | `geometry`, `skeleton` (+11 optional) |
| `point_capture_biharmonic` | KineFX Point Capture Biharmonic (kinefx::pointcapturebiharmonic) — `geometry`（input 0）を `skeleton`（input 1）に双調和ポイントクラウドキャプチャします。 | `geometry`, `skeleton` (+3 optional) |
| `joint_capture_paint` | KineFX Joint Capture Paint (kinefx::jointcapturepaint) — `skeleton`（input 1）に対して `geometry`（input 0）上の boneCapture ウェイトを初期化/正規化します。 | `geometry`, `skeleton` (+5 optional) |
| `capture_packed_geo` | KineFX Capture Packed Geo (kinefx::capturepackedgeo) — `skeleton`（input 1）に対して `geometry`（input 0）のキャプチャを転送/パックします。オプションで入力のパック、名前によるマッチング、結果のアンパックを行います。 | `geometry`, `skeleton` (+13 optional) |
| `capture_proximity` | Classic Capture Proximity (captureproximity) — `geometry`（input 0）を `skeleton`（input 1、ポイントごとの transform がリージョンを供給する KineFX スケルトン）上のキャプチャリージョンへ近接キャプチャします。 | `geometry`, `skeleton` (+18 optional) |
| `bone_capture` | Classic Capture (capture) — `skeleton`（input 1）上のキャプチャリージョンから `geometry`（input 0）にキャプチャウェイトを割り当てます。 | `geometry`, `skeleton` (+13 optional) |
| `bone_capture_lines` | Classic Bone Capture Lines (bonecapturelines) — `skeleton`（input 0）からクラシックなキャプチャリージョンのラインジオメトリ（boneCapture を保持）を生成し、クラシックなキャプチャソルバーに供給します。 | `skeleton` (+17 optional) |
| `capture_region` | Classic Capture Region (cregion) — 新規 /obj geo 内に 1 つのキャプチャリージョンプリミティブ（transform を持つチューブ）を出力する 0 入力の SOURCE です。 | `name` (+7 optional) |
| `capture_mirror` | Classic Capture Mirror (capturemirror) — 既にキャプチャ済みの `geometry`（input 0）のキャプチャウェイトを平面を挟んでミラーリングし、ミラーしたリージョンを find/replace トークンでリネームします。 | `geometry` (+10 optional) |
| `capture_correct` | Classic Capture Correct (capturecorrect) — 既にキャプチャ済みの `geometry`（input 0）のキャプチャウェイトをクリーンアップします。古いリージョンの更新/削除、負/正のウェイトのクランプ、ポイントごとのインフルエンス数の制限、再正規化を行います。 | `geometry` (+14 optional) |
| `capture_override` | Classic Capture Override (captureoverride) — 既にキャプチャ済みの `geometry`（input 0）に対し、指定した `cregions` のキャプチャウェイトを上書きし、設定したウェイトで演算を適用します。 | `geometry` (+8 optional) |
| `name_from_capture_weight` | Labs Name From Capture Weight (labs::name_from_capture_weight::1.0) — 既にキャプチャ済みの `geometry`（input 0）に、各ポイントの支配的なキャプチャリージョン（最も大きい boneCapture ウェイト）からポイント `name` アトリビュートを書き込みます。 | `geometry` (+3 optional) |
| `skinning_converter` | Labs Skinning Converter (labs::skinning_converter::3.0) — 頂点アニメーション/デフォームする `geometry`（input 0、時間依存）をスケルトン + boneCapture スキニングウェイトに変換します（frame_start..frame_end にわたる DemBones 系のソルブ）。 | `geometry` (+18 optional) |
| `dembones_skinning_converter` | KineFX DemBones Skinning Converter (kinefx::dembones_skinningconverter) — ワイヤー接続のみ（構築はするが実行はユーザーが行う）: Alembic キャッシュされたデフォームメッシュをスケルトン + スキンウェイトに変換する DemBones 外部ソルブを構築・接続・設定しますが、実行は決して行いません（maps_baker と同様 — 外部/重量級のソルブはユーザーが実行します）。 | `geometry` (+17 optional) |
| `joint_deform` | KineFX Joint Deform (kinefx::jointdeform) — キャプチャ済みのスキンをジョイントトランスフォームでデフォームします。 | `skin`, `rest_skeleton`, `deform_skeleton` (+8 optional) |
| `bone_deform` | KineFX Bone Deform (bonedeform) — ボーン/ジョイントのキャプチャアトリビュートを使ってキャプチャウェイト付きジオメトリをデフォームします。 | `skin` (+12 optional) |
| `deform_skeleton_skin` | KineFX Deform Skeleton/Skin (kinefx::deformskelskin) — スケルトン（input 0）をポージングし、バインドされたスキン（オプションの input 1）を同時にデフォームして、変換後のリグ/スキンを出力します。 | `skeleton` (+12 optional) |
| `pose_space_deform_combine` | KineFX Pose-Space Deform Combine (posespacedeformcombine) — 複数の Pose-Space Deform 出力（input 0..N）を 1 つの補正結果にマージします。 | `geometry` (+3 optional) |
| `pose_space_edit_configure` | KineFX Pose-Space Edit Configure (posespaceeditconfigure) — ジオメトリ（input 0）上で Pose-Space Edit がシェイプ差分を計算する方法（デフォーム前/後、orient）を設定します。オプションで bone capture により再デフォームします。 | `geometry` (+7 optional) |
| `character_blend_shapes_add` | KineFX Character Blend Shapes Add (kinefx::characterblendshapesadd) — 新しいブレンドシェイプ（または中間）ターゲット（input 1）をベースメッシュ（input 0）にパックします。 | `base` (+10 optional) |
| `character_blend_shapes_core` | KineFX Character Blend Shapes Core (kinefx::characterblendshapescore) — 低レベルの加重ブレンド評価器です。input 0 = ベースメッシュ、input 1 = パックされたブレンドターゲット + ウェイト。 | `base`, `blend_targets` (+6 optional) |
| `character_blend_shapes_extract` | KineFX Character Blend Shapes Extract (kinefx::characterblendshapesextract) — パックされたブレンドシェイプ入力（input 0）から、指定した単一のブレンドシェイプ（または中間）ターゲットメッシュを抽出します。 | `blendshape_geo` (+5 optional) |
| `character_blend_shape_channels` | KineFX Character Blend Shape Channels (kinefx::characterblendshapechannels) — メッシュ（input 0）のブレンドシェイプチャンネルテーブル（ウェイト）を定義/更新します。オプションで 2 番目の入力から初期化します。 | `mesh` (+3 optional) |
| `character_blend_shapes` | KineFX Character Blend Shapes (kinefx::characterblendshapes) — オールインワンのブレンドシェイプノードです。input 0 = ベースメッシュ、input 1 = ブレンドシェイプメッシュ、input 2 = チャンネル定義。加重ブレンドを適用します。 | `mesh`, `blend_shapes`, `channels` (+4 optional) |
| `blend_shapes` | Classic Blend Shapes (SOP blendshapes::2.0) — ベースメッシュ（input 0）を 1 つ以上のターゲットシェイプ（input 1..N）へ加重モーフィングします。 | `base` (+14 optional) |
| `secondary_motion` | KineFX Secondary Motion (kinefx::secondarymotion) — アニメーションスケルトン（input 0）にオーバーラップ/ジグル/スプリングのフォロースルーを追加します。 | `skeleton` (+21 optional) |
| `dynamic_warp` | KineFX Dynamic Warp (kinefx::dynamicwarp) — マッチしたアトリビュートに対する動的時間伸縮（dynamic time warping）を使って、ソースアニメーション（input 1）をリファレンスアニメーション（input 0）に合わせてタイムワープします。 | `reference_motion`, `source_motion` (+12 optional) |
| `skeleton_deform` | KineFX/Classic Deform (SOP `deform`) — `skel_root_path`（シーン内のノード参照）を通じて参照されるスケルトンによって、キャプチャウェイト付きジオメトリ（input 0）をデフォームします。 | `skin` (+15 optional) |
| `motion_clip` | KineFX MotionClip — フレーム範囲にわたってサンプリングしたアニメーションスケルトン（input 0）を、単一フレームのパックされた motionclip（チャンネルプリミティブ）に PACK します。 | `skeleton` (+17 optional) |
| `motion_clip_create` | KineFX MotionClip Create — ライブ SOP（mode single/fetchsop + source_sop）、クリップライブラリ、またはインポートした .bgeo/FBX クリップから motionclip を構築します。 | 18 optional |
| `motion_clip_compute_create` | KineFX Compute MotionClip Create — `source_sop`（Houdini ノードパス）のアニメーションスケルトンを、compute エンジンを使ってフレーム範囲にわたり motionclip にパックします（ジオメトリ入力 0）。 | `parent` (+5 optional) |
| `motion_clip_compute_retime` | KineFX Compute MotionClip Retime — compute エンジン経由で motionclip（input 0）をリタイムします。shift / 絶対時間 / フレーム / 速度に対応し、オプションでトリムと出力範囲/サンプルレートのリサンプリングを行います。 | `motionclip` (+22 optional) |
| `motion_clip_retime` | KineFX MotionClip Retime — motionclip（input 0）をリタイムします。shift / 絶対時間 / フレーム / 速度に対応し、オプションでトリム、フレームごとの時間/フレーム/速度の上書き、出力範囲/サンプルレートのリサンプリングを行います。 | `motionclip` (+27 optional) |
| `motion_clip_velocity` | KineFX MotionClip Compute Velocity — motionclip（input 0）上でジョイントごとの速度を計算します。オプションの `rest_frame`（input 1）でレストポーズを与えます。 | `motionclip` (+13 optional) |
| `motion_clip_cycle` | KineFX MotionClip Cycle — motionclip（input 0）を前後に繰り返してループを構築します。ロコモーションの連続性（shift/velocity/mirror）と継ぎ目でのポーズブレンドに対応します。 | `motionclip` (+18 optional) |
| `motion_clip_evaluate` | KineFX MotionClip Evaluate — motionclip（input 0）をあるフレームでサンプリングし、ライブスケルトンポーズ（現在のフレームまたは任意のフレーム）に戻します。オプションで COM 出力と終端挙動に対応します。 | `motionclip` (+14 optional) |
| `motion_clip_extract` | KineFX MotionClip Extract — motionclip（input 0）からポーズを、フレーム範囲にわたるフレームごとのスケルトンまたはモーショントレイルとして抽出します。 | `motionclip` (+16 optional) |
| `motion_clip_key_poses` | KineFX MotionClip Extract Key Poses — motionclip（input 0）をそのキーポーズ（割合または数で指定）に削減し、抽出またはタグ付けします。 | `motionclip` (+17 optional) |
| `motion_clip_locomotion` | KineFX MotionClip Extract Locomotion — motionclip（input 0）のルートロコモーションをその場モーションから分離します（compute / prim / joint ソース）。オプションで地面の軌跡を抽出したり、クリップをその場で平坦化したりします。 | `motionclip` (+15 optional) |
| `motion_clip_merge` | KineFX MotionClip Merge — 2 つの motionclip（input 0 + オプションの input 1 の `merge_clip`）を 1 つのクリップストリームにマージします。 | `input` (+5 optional) |
| `motion_clip_pose_delete` | KineFX MotionClip Pose Delete — motionclip（input 0）からポーズ（および/またはジョイント）を、フレーム範囲、フレームパターン、ポーズ範囲、またはポーズグループで削除します。 | `motionclip` (+13 optional) |
| `motion_clip_pose_insert` | KineFX MotionClip Pose Insert — 単一のスケルトンポーズ（`pose`、input 1）を motionclip（input 0）のあるフレームに挿入します。 | `motionclip`, `pose` (+3 optional) |
| `motion_clip_sequence` | KineFX MotionClip Sequence — 2 つの motionclip を端から端へ連結します。`first`（input 0）の次に `second`（input 1）を配置し、ロコモーションの連続性とブレンドされた継ぎ目に対応します。 | `first`, `second` (+18 optional) |
| `motion_clip_blend` | KineFX MotionClip Blend — `layer` motionclip（input 1）を `base` motionclip（input 0）の上に、フェードイン/フェードアウトのエンベロープとジョイントごとのブレンド効果でレイヤーします。 | `base`, `layer` (+19 optional) |
| `motion_clip_unpack` | KineFX MotionClip Unpack — motionclip（input 0）をライブのアニメーションスケルトン（単一フレーム/範囲/現在のフレーム）またはモーショントレイルにアンパックし、`time` ポイントアトリビュートを保持します。 | `motionclip` (+20 optional) |
| `motion_clip_update` | KineFX MotionClip Update — `poses`（input 1）からの新しいポーズで motionclip（input 0）を更新します。`poses` は `time` ポイントアトリビュートを必ず保持するアンパック済みスケルトン STREAM です（例: motion_clip_unpack の出力）。 | `motionclip`, `poses` (+9 optional) |
| `motion_clip_info` | KineFX MotionClip Create Clip Info — motionclip（オプションの input 0）が `clipinfo` ディテールアトリビュートを持つことを保証し、欠落している場合はクリップの `time` プリムアトリビュートから導出します。 | 3 optional |
| `motion_mixer_retime` | KineFX Motion Mixer Retime — motion-mixer / motionclip シーン（input 0）を絶対フレーム、時間、再生速度、またはホールドでリタイムします。 | `input` (+9 optional) |
| `motion_mixer_smooth` | KineFX Motion Mixer Smooth — `pattern` で選択した motion-mixer / motionclip シーン（input 0）のチャンネルを、t/r/s 成分にわたって Butterworth フィルタリングします。 | `input` (+9 optional) |
| `motion_mixer_transform` | KineFX Motion Mixer Transform — `group` で選択した motion-mixer / motionclip シーン（input 0）のチャンネルに TRS（+shear/pivot）トランスフォームを適用します。 | `input` (+10 optional) |
| `fbx_character_import` | KineFX FBX Character Import — FBX キャラクター一式（output 0 にスケルトン、output 1 にスキン、output 2 にブレンドシェイプ）を新規 /obj geo にインポートします。オプションで 2 つ目の FBX からアニメーションをマージします。 | `name`, `fbx_file` (+15 optional) |
| `fbx_anim_import` | KineFX FBX Animation Import — FBX ファイルからアニメーションスケルトン（モーションクリップ）を新規 /obj geo にインポートします。 | `name`, `fbx_file` (+14 optional) |
| `fbx_skin_import` | KineFX FBX Skin Import — FBX キャラクターからスキニング済みメッシュ（`boneCapture` ウェイトを保持）を新規 /obj geo にインポートします。 | `name`, `fbx_file` (+8 optional) |
| `gltf_character_import` | KineFX glTF Character Import — glTF/glb キャラクター一式（output 0 にスケルトン、output 1 にスキン、output 2 にブレンドシェイプ）を新規 /obj geo にインポートします。 | `name`, `gltf_file` (+7 optional) |
| `gltf_anim_import` | KineFX glTF Animation Import — glTF/glb ファイルからアニメーションスケルトン（モーションクリップ）を新規 /obj geo にインポートします。 | `name`, `gltf_file` (+5 optional) |
| `gltf_skin_import` | KineFX glTF Skin Import — glTF/glb キャラクターからスキニング済みメッシュ（`boneCapture` ウェイトを保持）を新規 /obj geo にインポートします。 | `name`, `gltf_file` (+2 optional) |
| `usd_character_import` | KineFX USD Character Import — USD ファイルから USDSkel キャラクター（output 0 にスケルトン、output 1 にスキン、output 2 にブレンドシェイプ）を新規 /obj geo にインポートします（/stage LOP ではなくファイルソースを強制）。 | `name`, `usd_file` (+7 optional) |
| `usd_anim_import` | KineFX USD Animation Import — USDSkel ファイルからアニメーションスケルトン（モーションクリップ）を新規 /obj geo にインポートします（ファイルソースを強制）。 | `name`, `usd_file` (+7 optional) |
| `usd_skin_import` | KineFX USD Skin Import — USDSkel キャラクターからスキニング済みメッシュ（`boneCapture` ウェイトを保持）を新規 /obj geo にインポートします（ファイルソースを強制）。 | `name`, `usd_file` (+3 optional) |
| `mocap_import` | KineFX Mocap Import — 生のモーションキャプチャデータ（Biovision BVH、Acclaim ASF+AMC、または Motion-Analysis TRC）をアニメーションスケルトンとして新規 /obj geo にインポートします。 | `name` (+20 optional) |
| `clip_import` | KineFX Clip Import — ディスクから .bclip/.clip の CHOP モーションクリップを読み込み、（オプションで `skeleton` input 0 が与えられた場合）そのスケルトンに適用します。それ以外の場合はクリップを新規 /obj geo に出力します。 | `name`, `file` (+5 optional) |
| `retarget_biped_fbx` | KineFX Retarget Biped FBX — バイペッド FBX をインポートし、そのアニメーションを KineFX バイペッドテンプレート（output 0 にスケルトン、output 1 にアニメーション、output 2 にスキン）へ新規 /obj geo 内でリターゲットします。 | `name`, `fbx_file` (+9 optional) |
| `character_io` | KineFX Character IO — KineFX キャラクターをその構成要素から組み立てます。input0 = レストの `geometry`、input1 = `capture_pose` スケルトン（オプション）、input2 = `animated_pose` スケルトン/motionclip（オプション）。 | `geometry` (+13 optional) |
| `fbx_anim_export` | KineFX FBX Animation Output — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry` (+17 optional) |
| `fbx_character_export` | KineFX FBX Character Output — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `skin_geo`, `capture_pose` (+20 optional) |
| `gltf_character_export` | KineFX glTF Character Output — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `skin_geo`, `capture_pose` (+13 optional) |
| `clip_export` | KineFX Clip Export — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry` (+8 optional) |
| `scene_character_export` | KineFX Scene Character Export — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry`, `skeleton` (+7 optional) |
| `retarget_fbx_export` | KineFX Retarget FBX Export — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry` (+18 optional) |
| `classic_bone` | KineFX/Classic Bone (OBJ `bone`) — 1 つのクラシックな Bone オブジェクトを作成します。長さでパラメータ化されたボーンで、bonelink 表示と調整可能な capture / deform キャプチャリージョンのシリンダーを持ちます（KineFX 以前のスキニングプリミティブ）。 | 14 optional |
| `dembones_skinning_export` | KineFX/Classic DemBones Skinning Converter ROP (/out `dembones_skinningconverter`) — ワイヤー接続のみ（構築はするが実行はユーザーが行う）: アニメーション Alembic キャッシュ（+ オプションのバインドポーズ FBX）をスケルトン + スキンウェイト付き FBX に変換する DemBones 外部ソルブを構築・設定しますが、実行は決して行いません（maps_baker と同様 — 重量級の外部ソルブはユーザーが実行します）。 | 19 optional |
| `deform_bone_rig_biped_arm` | KineFX/Classic Deform Bone Rig — Biped Arm (OBJ `deform_bone_rig_biped_arm`) — バイペッドの腕用の既製のクラシックボーンデフォーメーションリグ（キャプチャリージョン付きの鎖骨/上腕/前腕/手首ボーン）をインスタンス化します。 | 9 optional |
| `deform_bone_rig_biped_hand_4f_2s` | KineFX/Classic Deform Bone Rig — Biped Hand, 4 Fingers / 2 Segments (OBJ `deform_bone_rig_biped_hand_4f_2s`) — 4 本指・2 セグメントの手用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_biped_hand_4f_3s` | KineFX/Classic Deform Bone Rig — Biped Hand, 4 Fingers / 3 Segments (OBJ `deform_bone_rig_biped_hand_4f_3s`) — 4 本指・3 セグメントの手用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_biped_hand_5f_3s` | KineFX/Classic Deform Bone Rig — Biped Hand, 5 Fingers / 3 Segments (OBJ `deform_bone_rig_biped_hand_5f_3s`) — 5 本指・3 セグメントのフルハンド用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_biped_head_and_neck` | KineFX/Classic Deform Bone Rig — Biped Head and Neck (OBJ `deform_bone_rig_biped_head_and_neck`) — バイペッドの頭 + 首チェーン用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_biped_leg` | KineFX/Classic Deform Bone Rig — Biped Leg (OBJ `deform_bone_rig_biped_leg`) — バイペッドの脚用の既製のクラシックボーンデフォーメーションリグ（キャプチャリージョン付きの大腿/脛/足ボーン）です。 | 9 optional |
| `deform_bone_rig_biped_spine_3pc` | KineFX/Classic Deform Bone Rig — Biped Spine, 3 Pieces (OBJ `deform_bone_rig_biped_spine_3pc`) — バイペッドの背骨用の既製の 3 セグメントクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_biped_spine_5pc` | KineFX/Classic Deform Bone Rig — Biped Spine, 5 Pieces (OBJ `deform_bone_rig_biped_spine_5pc`) — バイペッドの背骨用の既製の 5 セグメントクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_quadruped_back_leg` | KineFX/Classic Deform Bone Rig — Quadruped Back Leg (OBJ `deform_bone_rig_quadruped_back_leg`) — 四足動物の後ろ脚用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_quadruped_front_leg` | KineFX/Classic Deform Bone Rig — Quadruped Front Leg (OBJ `deform_bone_rig_quadruped_front_leg`) — 四足動物の前脚用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_quadruped_head_and_neck` | KineFX/Classic Deform Bone Rig — Quadruped Head and Neck (OBJ `deform_bone_rig_quadruped_head_and_neck`) — 四足動物の頭 + 首チェーン用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_quadruped_ik_spine` | KineFX/Classic Deform Bone Rig — Quadruped IK Spine (OBJ `deform_bone_rig_quadruped_ik_spine`) — 四足動物の IK スパインチェーン用の既製のクラシックボーンデフォーメーションリグです。 | 9 optional |
| `deform_bone_rig_quadruped_tail` | KineFX Deform Bone Rig Quadruped Tail — 四足動物の尻尾チェーン用の /obj ボーンデフォームリグ HDA です（A_source: 0 入力、デフォルトのガイド/フックリグをクックします）。 | 11 optional |
| `deform_bone_rig_quadruped_toes_4f` | KineFX Deform Bone Rig Quadruped Toes (4 Fingers) — 4 本指の四足動物の足用の /obj ボーンデフォームリグ HDA です（A_source: 0 入力）。 | 11 optional |
| `deform_bone_rig_quadruped_toes_5f` | KineFX Deform Bone Rig Quadruped Toes (5 Fingers) — 5 本指の四足動物の足用の /obj ボーンデフォームリグ HDA です（A_source: 0 入力）。 | 11 optional |
| `deform_rig_biped_arm` | KineFX Deform Rig Biped Arm — バイペッドの腕用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力、デフォルトのマッスル/ガイドリグをクックします）。 | 14 optional |
| `deform_rig_biped_hand_4f_2s` | KineFX Deform Rig Biped Hand (4 Fingers, 2 Segments) — バイペッドの手用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_biped_hand_4f_3s` | KineFX Deform Rig Biped Hand (4 Fingers, 3 Segments) — バイペッドの手用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_biped_hand_5f_3s` | KineFX Deform Rig Biped Hand (5 Fingers, 3 Segments) — バイペッドの手用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_biped_head_and_neck` | KineFX Deform Rig Biped Head and Neck — バイペッドの頭+首用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 21 optional |
| `deform_rig_biped_leg` | KineFX Deform Rig Biped Leg — バイペッドの脚用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_biped_spine_3pc` | KineFX Deform Rig Biped Spine (3 Pieces) — 3 ピースのバイペッド背骨用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_biped_spine_5pc` | KineFX Deform Rig Biped Spine (5 Pieces) — 5 ピースのバイペッド背骨用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_back_leg` | KineFX Deform Rig Quadruped Back Leg — 四足動物の後ろ脚用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_front_leg` | KineFX Deform Rig Quadruped Front Leg — 四足動物の前脚用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_head_and_neck` | KineFX Deform Rig Quadruped Head and Neck — 四足動物の頭+首用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 21 optional |
| `deform_rig_quadruped_ik_spine` | KineFX Deform Rig Quadruped IK Spine — 四足動物の IK スパイン用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_tail` | KineFX Deform Rig Quadruped Tail — 四足動物の尻尾用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_toes_4f` | KineFX Deform Rig Quadruped Toes (4 Fingers) — 4 本指の四足動物の足用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `deform_rig_quadruped_toes_5f` | KineFX Deform Rig Quadruped Toes (5 Fingers) — 5 本指の四足動物の足用の /obj マッスルデフォームリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `toon_character_deform_rig` | KineFX Toon Character Deform Rig (toon_character_deform_rig) — レガシーの既製フルトゥーンキャラクターをインスタンス化する 0 入力の OBJ PRESET です。キャプチャ済みの `skin` サブオブジェクトを駆動するボディパーツのボーンリグ（背骨 / 腕 / 脚 / 頭+首 / 手）です。 | 5 optional |
| `bone_link` | KineFX Bone Link (bonelink) — 新規 /obj geo 内にクラシックなボーンリンクジオメトリ（ボーンの両端の間に描かれるテーパー状のリンク形状。オプションで packed-bone / fin / proxy / capture の可視化付き）を出力する 0 入力の SOURCE です。 | 13 optional |
| `bone_solidify` | KineFX Bone Solidify (bonesolidify) — 入力スキン `mesh`（input 0）を、リグにバインドされたソリッドなテトメッシュにテトラ化します。FEM / ソフトボディ風のボーンデフォーメーション用です。 | `mesh` (+19 optional) |
| `capture_attribute_unpack` | KineFX Capture Attribute Unpack (captureattribunpack) — `geometry`（input 0）上のパックされたキャプチャアトリビュート（デフォルト `boneCapture`）を、個別の `_index` + `_data` コンポーネントアトリビュートに展開し、生のウェイトを汎用のアトリビュートツールで編集できるようにします。 | `geometry` (+8 optional) |
| `capture_attribute_pack` | KineFX Capture Attribute Pack (captureattribpack) — `geometry`（input 0）上の個別のキャプチャ `_index` + `_data` コンポーネントアトリビュートを、単一のパックされたキャプチャアトリビュート（デフォルト `boneCapture`）に戻して統合します。 | `geometry` (+8 optional) |
| `capture_layer_paint` | KineFX Capture Layer Paint (capturelayerpaint::2.0) — アクティブなキャプチャリージョンについて `geometry`（input 0）上のクラシックなキャプチャウェイトを編集/正規化します。ブラシはビューポートツールのため、このデータ専用エンドポイントはリージョン選択 / 正規化 / キャプチャタイプの制御のみを公開し、再正規化したリグをそのまま通します。 | `geometry` (+11 optional) |
| `post_anim_deform` | Labs Post Animation Deform (labs::post_anim_deform) — レストメッシュ（input 1）とそのデフォーム版（input 2）の間のデフォーメーション差分を、対応する `deforming` メッシュ（input 0）に適用します。オプションで orientation/transform アトリビュートを転送します。 | `deforming`, `rest`, `deformed` (+6 optional) |
| `neuron_mocap` | Labs Neuron Mocap (labs::neuron_mocap) — Perception Neuron のライブ mocap ストリーム（キャラクター名 / IP / ポート / データフォーマット / アクターインデックス）を設定し、受信したスケルトンを出力する 0 入力の SOURCE（新規 /obj geo）です。 | `name` (+5 optional) |
| `rokoko_mocap` | Labs Rokoko Mocap (labs::rokoko_mocap) — Rokoko Smartsuit のライブ mocap ストリーム（IP / ポート / アクター / スーツ名）とオプションの録画ファイルを設定し、受信したスケルトンを出力する 0 入力の SOURCE（新規 /obj geo）です。 | `name` (+6 optional) |
| `dembones_skinning_external` | Labs DemBones Skinning Converter (labs::dembones_skinningconverter) — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry` (+20 optional) |
| `dembones_skinning_bake` | DemBones Skinning Converter、ネイティブ SOP ライター (dembones_skinningconverter::1.0) — ワイヤー接続のみ（構築はするが実行はユーザーが行う）。 | `geometry` (+21 optional) |
| `skin_properties` | KineFX Skin Properties (skinproperties) — 入力スキン（input 0）上にポイントごとのマッスル/スキン SOLVER プロパティアトリビュートを付与します。surface & solid の stiffness / damping / bend-stiffness / mass-density / sliding-rate を、オプションでマスク・ブレンドしつつ、マテリアル `preset` とともに設定します。 | `geometry` (+15 optional) |
| `skin_solidify` | KineFX Skin Solidify (skinsolidify::2.0) — 入力スキンサーフェス（input 0）の周りに層状の SOLID テトシェルを構築します。FEM / クロス風のスキンシミュレーション用です。`skin_thickness` + `num_layers` がシェルの深さを設定し、要素サイズのレバー（`min_size`/`max_size`/`rel_density`/`gradation`）がテト密度を制御し、スムージングのリラクゼーション（`iterations`/`step_size`）が内部ウェイトをクリーンアップします。 | `geometry` (+15 optional) |
| `skin_deform` | KineFX Skin Deform (skindeform) — 入力スキン（input 0）に対するマッスルを考慮したスキン仕上げ処理です。スキンウェイトを下層のマッスルモーションに向けてスムージングする muscle-blur パスと、スキンをマッスル上でスライドさせるオプションの skin-sliding リラクゼーション（基準フレームに対して解決）を行います。 | `geometry` (+12 optional) |
| `animation_rig_biped_arm` | KineFX Animation Rig Biped Arm — バイペッドの腕用の /obj アニメーション（コントロール）リグ HDA です（A_source: 0 入力、デフォルトの FK/IK コントロールリグをクックします）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_hand_4f_2s` | KineFX Animation Rig Biped Hand (4 Fingers, 2 Segments) — バイペッドの手用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_hand_4f_3s` | KineFX Animation Rig Biped Hand (4 Fingers, 3 Segments) — バイペッドの手用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_hand_5f_3s` | KineFX Animation Rig Biped Hand (5 Fingers, 3 Segments) — バイペッドの手用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_head_and_neck` | KineFX Animation Rig Biped Head and Neck — バイペッドの頭+首用の /obj アニメーションリグ HDA です（A_source: 0 入力、頭/首/顎/眼の look-at コントロールをクックします）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_leg` | KineFX Animation Rig Biped Leg — バイペッドの脚用の /obj アニメーションリグ HDA です（A_source: 0 入力、デフォルトの FK/IK コントロールリグをクックします）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_spine_3pc` | KineFX Animation Rig Biped Spine (3 Pieces) — 3 ピースのバイペッド背骨用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_biped_spine_5pc` | KineFX Animation Rig Biped Spine (5 Pieces) — 5 ピースのバイペッド背骨用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_character_placer` | KineFX Animation Rig Character Placer — キャラクター全体を配置する /obj ルート配置リグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color が配置コントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_back_leg` | KineFX Animation Rig Quadruped Back Leg — 四足動物の後ろ脚用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_front_leg` | KineFX Animation Rig Quadruped Front Leg — 四足動物の前脚用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_head_and_neck` | KineFX Animation Rig Quadruped Head and Neck — 四足動物の頭+首用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_ik_spine` | KineFX Animation Rig Quadruped IK Spine — 四足動物の IK スパイン用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_tail` | KineFX Animation Rig Quadruped Tail — 四足動物の尻尾用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_toes_4f` | KineFX Animation Rig Quadruped Toes (4 Fingers) — 4 本指の四足動物の足用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `animation_rig_quadruped_toes_5f` | KineFX Animation Rig Quadruped Toes (5 Fingers) — 5 本指の四足動物の足用の /obj アニメーションリグ HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `auto_rig_biped_arm` | KineFX Auto Rig Biped Arm — デフォルトからバイペッドの腕のコントロールリグ一式を組み立てる /obj オートリグビルダー HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `auto_rig_biped_hand_4f_2s` | KineFX Auto Rig Biped Hand (4 Fingers, 2 Segments) — デフォルトからバイペッドの手のコントロールリグ一式を組み立てる /obj オートリグビルダー HDA です（A_source: 0 入力）。control_scale/control_lod/control_color がコントロールのサイズとスタイルを設定し、hook_object がシーン内の親オブジェクトを参照します。 | `name` (+14 optional) |
| `auto_rig_biped_hand_4f_3s` | KineFX Auto Rig Biped Hand (4 Fingers, 3 Segments) — デフォルトの 4 本指バイペッド手コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 17 optional |
| `auto_rig_biped_hand_5f_3s` | KineFX Auto Rig Biped Hand (5 Fingers, 3 Segments) — デフォルトの 5 本指バイペッド手コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 17 optional |
| `auto_rig_biped_head_and_neck` | KineFX Auto Rig Biped Head and Neck — デフォルトのバイペッド頭+首コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 16 optional |
| `auto_rig_biped_leg` | KineFX Auto Rig Biped Leg — デフォルトのバイペッド脚コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 19 optional |
| `auto_rig_biped_spine_3pc` | KineFX Auto Rig Biped Spine (3 Pieces) — デフォルトの 3 ピースバイペッド背骨コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 15 optional |
| `auto_rig_biped_spine_5pc` | KineFX Auto Rig Biped Spine (5 Pieces) — デフォルトの 5 ピースバイペッド背骨コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 15 optional |
| `auto_rig_quadruped_back_leg` | KineFX Auto Rig Quadruped Back Leg — デフォルトの四足動物後ろ脚コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 19 optional |
| `auto_rig_quadruped_front_leg` | KineFX Auto Rig Quadruped Front Leg — デフォルトの四足動物前脚コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 19 optional |
| `auto_rig_quadruped_head_and_neck` | KineFX Auto Rig Quadruped Head and Neck — デフォルトの四足動物頭+首コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 18 optional |
| `auto_rig_quadruped_ik_spine` | KineFX Auto Rig Quadruped IK Spine — デフォルトの四足動物 IK スパインコントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 16 optional |
| `auto_rig_quadruped_tail` | KineFX Auto Rig Quadruped Tail — デフォルトの四足動物尻尾コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 15 optional |
| `auto_rig_quadruped_toes_4f` | KineFX Auto Rig Quadruped Toes (4 Fingers) — デフォルトの 4 本指四足動物足コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 18 optional |
| `auto_rig_quadruped_toes_5f` | KineFX Auto Rig Quadruped Toes (5 Fingers) — デフォルトの 5 本指四足動物足コントロールリグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 18 optional |
| `auto_rig_character_placer` | KineFX Auto Rig Character Placer — リグを構築する元となる配置ガイドをレイアウトする /obj オートリグ HDA です（A_source: 0 入力）。 | 18 optional |
| `biped_auto_rig` | KineFX Biped Auto Rig — デフォルトのバイペッドコントロールリグ一式を構築する /obj ワンコール HDA です（A_source: 0 入力）。 | 24 optional |
| `auto_rig_eye` | KineFX Auto Rig Eye — 単一の眼リグを構築する /obj オートリグ HDA です（A_source: 0 入力）。 | 14 optional |
| `impostor_camera_rig` | KineFX Labs Impostor Camera Rig — インポスターベイクの撮影元となるマルチビューカメラリグを構築する /obj リグ HDA です（A_source: 0 入力）。 | 9 optional |
| `mocap_acclaim` | KineFX Mocap Acclaim — Acclaim ASF/AMC モーションキャプチャ用の /obj mocap インポート HDA です（A_source: 0 入力。スケルトンが設定されるまでは緑の空状態でクックします）。 | 17 optional |
| `mocap_rig_biped_arm` | KineFX Mocap Rig Biped Arm — mocap スケルトンからバイペッドの腕アニメーションリグを駆動する /obj mocap リターゲットリグ HDA です（A_source: 0 入力）。 | 18 optional |
| `mocap_rig_biped_head_and_neck` | KineFX Mocap Rig Biped Head and Neck — mocap スケルトンからバイペッドの頭+首アニメーションリグを駆動する /obj mocap リターゲットリグ HDA です（A_source: 0 入力）。 | 17 optional |
| `mocap_rig_biped_leg` | KineFX Mocap Rig Biped Leg — mocap スケルトンからバイペッドの脚アニメーションリグを駆動する /obj mocap リターゲットリグ HDA です（A_source: 0 入力）。 | 23 optional |
| `mocap_rig_biped_spine_3pc` | KineFX Mocap Rig Biped Spine (3 Pieces) — mocap スケルトンから 3 ピースのバイペッド背骨アニメーションリグを駆動する /obj mocap リターゲットリグ HDA です（A_source: 0 入力）。 | 19 optional |
| `mocap_rig_biped_spine_5pc` | KineFX Mocap Rig Biped Spine (5 Pieces) — mocap スケルトンから 5 ピースのバイペッド背骨アニメーションリグを駆動する /obj mocap リターゲットリグ HDA です（A_source: 0 入力）。 | 23 optional |
| `mocap_biped_1` | KineFX MoCap Biped 1 — ベイク済みのロコモーションクリップを持つ既製の MoCap Biped テストキャラクターです（A_source: 素の状態で構築、入力接続 0）。 | 10 optional |
| `mocap_biped_2` | KineFX MoCap Biped 2 — 大規模なベイク済みクリップライブラリを持つ既製の MoCap Biped テストキャラクターです（A_source: 素の状態で構築、入力接続 0）。 | 10 optional |
| `mocap_biped_3` | KineFX MoCap Biped 3 — カテゴリ分けされたクリップライブラリとモーションマッチングを備えた高度な既製 MoCap Biped テストキャラクターです（A_source: 素の状態で構築、入力接続 0）。 | 14 optional |
| `quadruped_auto_rig_4f` | KineFX Quadruped Auto Rig (4 Toes) — デフォルトの 4 本指四足動物コントロールリグ一式を構築する /obj ワンコール HDA です（A_source: 0 入力）。 | 28 optional |
| `quadruped_auto_rig_5f` | KineFX Quadruped Auto Rig (5 Toes) — デフォルトの 5 本指四足動物コントロールリグ一式を構築する /obj ワンコール HDA です（A_source: 0 入力）。 | 28 optional |
| `toon_character` | KineFX Toon Character — デフォルトからリグ済みのフルトゥーンキャラクター（オートリグ + フェイス + mocap）を構築する /obj HDA です（A_source: 0 入力）。 | 18 optional |
| `constraint_begin` | KineFX Constraint Get World Space Begin (constraintbegin) — CHOP コンストレイントネットワークの START です。`object` のワールドトランスフォームを t/r/s トラック（9 トラック）として出力し、下流のコンストレイント CHOP がそれらを合成します。 | 6 optional |
| `constraint_object` | KineFX Constraint Object (constraintobject) — `target` のワールドトランスフォームを t/r/s トラック（9）として出力します。オプションで `reference` に対する相対で表現します。 | 6 optional |
| `constraint_object_pretransform` | KineFX Constraint Object Pretransform (constraintobjectpretransform) — `target` のプリトランスフォーム（オブジェクトのレスト/ピボットオフセット）を t/r/s トラック（9）として出力します。 | 5 optional |
| `constraint_object_offset` | KineFX Constraint Object Offset (constraintobjectoffset) — `reference` に対する `target` のオフセットトランスフォームを t/r/s トラック（9）として、`channel_mask` でマスクして出力します。 | 9 optional |
| `constraint_get_world_space` | KineFX Constraint Get World Space (constraintgetworldspace) — `object` の WORLD 空間トランスフォームを t/r/s トラック（9）として出力します。 | 5 optional |
| `constraint_get_parent_space` | KineFX Constraint Get Parent Space (constraintgetparentspace) — `object` の PARENT 空間トランスフォームを t/r/s トラック（9）として出力します。`parent_bone` が親ボーンの規約を選択します。 | 6 optional |
| `constraint_get_local_space` | KineFX Constraint Get Local Space (constraintgetlocalspace) — `object` の LOCAL 空間トランスフォームを t/r/s トラック（9）として出力します。`mode` がローカル空間の規約を選びます。 | 6 optional |
| `constraint_look_at` | KineFX Constraint Look At (constraintlookat) — `look_up_axis_*` をアップターゲットに向けたまま、`look_at_axis` を look-at 位置に向ける回転を出力します（9 トラック）。 | 15 optional |
| `constraint_path` | KineFX Constraint Path (constraintpath) — `sop_path` のカーブに沿ってパラメトリックな `position` に乗るトランスフォームを、look-at/look-up 設定で向き付けして出力します（9 トラック）。 | 21 optional |
| `constraint_points` | KineFX Constraint Points (constraintpoints) — `sop_path` の SOP のポイント（`group`、または `search_distance`/`search_max_points` 内の最近接）にアタッチされたトランスフォームを、look-at/look-up 設定で向き付けして出力します（9 トラック）。 | 22 optional |
| `constraint_export` | KineFX Constraint Export (constraintexport) — 合成されたトランスフォームを `constraints_path` のコンストレイントオブジェクトにエクスポートして、コンストレイントネットワークを終端します。`enable_constraints` でライブに切り替えます。 | 4 optional |
| `constraint_blend` | KineFX Constraint Blend (constraintblend) — 2 つ以上のコンストレイントトランスフォームストリームをブレンドします。 | `input` (+5 optional) |
| `constraint_sequence` | KineFX Constraint Sequence (constraintsequence) — コンストレイントストリームのチェーンを `blend` で順次ブレンドします。 | `input` (+5 optional) |
| `constraint_offset` | KineFX Constraint Offset (constraintoffset) — `input1`（input 1）のオフセットトランスフォームを、`input`（input 0）のベーストランスフォームに `blend` で適用します。 | `input`, `input1` (+6 optional) |
| `constraint_parent` | KineFX Constraint Parent (constraintparent) — 子トランスフォームを親トランスフォームの下に合成します（CHOP のペアレンティングプリミティブ）。 | `input` (+3 optional) |
| `constraint_parent_extended` | KineFX Constraint Parent Extended (constraintparentx) — `write_mask`（書き込むチャンネルの int ビットマスク、デフォルト 511）付きのペアレンティングです。 | `input` (+4 optional) |
| `constraint_simple_blend` | KineFX Constraint Simple Blend (constraintsimpleblend) — 2 つのコンストレイントストリームを `blend` で軽量にブレンドします。 | `input` (+5 optional) |
| `constraint_offset_blend` | KineFX Constraint Offset Blend (constraintoffsetblend) — 最大 4 つのコンストレイントストリームにわたってオフセットを `blend` でブレンドします。 | `input` (+7 optional) |
| `constraint_surface` | KineFX Constraint Surface (constraintsurface) — `sop_path` の SOP の SURFACE に貼り付いたトランスフォームを出力する CHOP です。位置は UV 座標（`uv_attribute` 上の `uv`）、位置（`position_attribute` 上の `p`）、または `search_distance`/`search_max_points` 内の最近接ポイントで指定し、look-at / look-up 設定で向き付けします。 | 26 optional |
| `constraint_transform` | KineFX Constraint Transform (constrainttransform) — `translate`/`rotate`/`scale`（`transform_order`/`rotation_order` 付き）、ピボット（`pivot` / `pivot_rotate`）、および `mode`/`pivot_mode` から構築した明示的なトランスフォームを出力する CHOP です。`invert` は結果を反転します。 | 15 optional |
| `constraint_pose` | KineFX Pose (pose) — 保存された静的ポーズを t/r/s トランスフォームトラックとして出力する Constraints タブの CHOP です（`transform_order`/`rotation_order` 付きの `translate`/`rotate`/`scale` から）。 | 8 optional |
| `jiggle` | KineFX Jiggle (jiggle) — `input`（input 0、tx/ty/tz チャンネルを必ず保持すること）のトランスフォームストリームに二次的なジグルモーションを追加する CHOP です。 | `input` (+7 optional) |
| `lag` | KineFX Lag (lag) — `input`（input 0）のチャンネルストリームをスムージング/遅延させる CHOP です。 | `input` (+8 optional) |
| `channel_spring` | KineFX Spring (spring, CHOP) — `input`（input 0）のチャンネルストリームを質量-バネ系で駆動します。`spring_constant`、`mass`、`damping`、`method`（disp / force）、初期 `position` / `speed`、および入力から初期状態を初期化する `use_channel_condition` を使います。 | `input` (+8 optional) |
| `channel_pose_difference` | KineFX Pose Difference (posedifference, CHOP) — `input`（input 0）のポーズストリームと基準ポーズの差分を計算します。 | `input` (+3 optional) |
| `chop_wave` | CHOP Wave (wave) — フレーム範囲にわたって周期的な波形チャンネル（sine/triangle/ramp/square/pulse）を生成します。 | 16 optional |
| `chop_waveform` | CHOP Waveform (waveform) — constant/sine/square の波形チャンネルを生成します（データ駆動の波形ソース）。 | 13 optional |
| `chop_noise` | CHOP Noise (noise) — アニメーションするノイズチャンネル（sparse/perlin/harmonic/brownian/alligator）を生成します。 | 14 optional |
| `chop_constant` | CHOP Constant (constant) — 定数値を保持するチャンネル（最大 4 つの名前付きチャンネル）を生成します。 | 10 optional |
| `chop_spline` | CHOP Spline (spline) — 範囲にわたってスプライン補間されたチャンネル（bezier/cubic）を生成します。 | 11 optional |
| `chop_pulse` | CHOP Pulse (pulse) — 範囲にわたって値のパルス列を生成します。 | 13 optional |
| `chop_channel` | CHOP Channel (channel) — 範囲にわたってパラメータチャンネル/キーフレームからサンプリングしたチャンネルを生成します。 | 11 optional |
| `chop_oscillator` | CHOP Oscillator (oscillator) — 入力チャンネルで駆動されるオーディオ風オシレーターです（入力 CHOP が必須）。 | `input` (+15 optional) |
| `chop_math` | CHOP Math (math) — チャンネルごと・CHOP 間の算術演算、ゲイン、リマップを行います。 | `input` (+19 optional) |
| `chop_function` | CHOP Function (function) — 入力チャンネルに数学関数（sqrt/trig/log/pow/...）を適用します。 | `input` (+12 optional) |
| `chop_filter` | CHOP Filter (filter) — 入力チャンネルに対する時間フィルタ（gaussian/box/edge/sharpen/despike）です。 | `input` (+9 optional) |
| `chop_limit` | CHOP Limit (limit) — 入力チャンネル値をクランプ/ループ/量子化します。 | `input` (+15 optional) |
| `chop_lag` | CHOP Lag (lag) — 入力チャンネルを lag/overshoot（バネ風の追従）でスムージングします。 | `input` (+11 optional) |
| `chop_lookup` | CHOP Lookup (lookup) — input 0 をインデックスとして input 1 の値をルックアップします。 | `input` (+9 optional) |
| `chop_cycle` | CHOP Cycle (cycle) — 入力チャンネルを前後に繰り返し/ミラーし、オプションでブレンドします。 | `input` (+13 optional) |
| `chop_blend` | CHOP Blend (blend) — 接続された入力にわたってチャンネルを加重ブレンドします。 | `input` (+10 optional) |
| `chop_merge` | CHOP Merge (merge) — 接続されたすべての入力のチャンネルを 1 つのストリームにマージします。 | `input` (+9 optional) |
| `chop_warp` | CHOP Warp (warp) — input 1 の warp チャンネルによって input 0 をタイムワープします。 | `input` (+7 optional) |
| `chop_resample` | CHOP Resample (resample) — 入力チャンネルを新しいレート/範囲にリサンプリングします。 | `input` (+14 optional) |
| `chop_shift` | CHOP Shift (shift) — 入力チャンネルを時間方向にシフト/スクロールします。 | `input` (+10 optional) |
| `chop_hold` | CHOP Hold (hold) — 入力チャンネルをホールド（サンプルアンドホールド）します。 | `input` (+5 optional) |
| `chop_spectrum` | CHOP Spectrum (spectrum) — 入力チャンネルを周波数領域に/から変換します。 | `input` (+11 optional) |
| `chop_multiply` | CHOP Multiply (multiply) — 接続されたすべての入力のチャンネルを掛け合わせます。 | `input` (+7 optional) |
| `chop_invert` | CHOP Invert (invert) — 入力チャンネル値を反転（逆数）します。 | `input` (+4 optional) |
| `chop_extend` | CHOP Extend (extend) — 入力チャンネルが範囲の前後でどのように延長されるかを設定します。 | `input` (+7 optional) |
| `chop_stretch` | CHOP Stretch (stretch) — 入力チャンネルを時間と値の方向にストレッチします。 | `input` (+12 optional) |
| `chop_trim` | CHOP Trim (trim) — 入力チャンネルをサブ範囲にトリムします。 | `input` (+9 optional) |
| `chop_area` | CHOP Area (area) — 入力チャンネルを積分します（面積 / 累積積分）。 | `input` (+13 optional) |
| `chop_envelope` | CHOP Envelope (envelope) — 入力チャンネルの振幅エンベロープを抽出します。 | `input` (+11 optional) |
| `chop_interp` | CHOP Interpolate (interp) — 接続された入力間を時間にわたって補間します。 | `input` (+11 optional) |
| `chop_delay` | CHOP Delay (delay) — 入力チャンネルの遅延・ゲイン付きエコーを追加します。 | `input` (+14 optional) |
| `chop_slope` | CHOP Slope (slope) — 入力チャンネルの傾き / 加速度（微分）を計算します。 | `input` (+6 optional) |
| `chop_fan` | CHOP Fan (fan) — 1 つのチャンネルを多数に展開、または多数のチャンネルを 1 つにまとめます。 | `input` (+8 optional) |
| `chop_count` | CHOP Count (count) — 入力チャンネルのしきい値交差回数をカウントします。 | `input` (+14 optional) |
| `chop_null` | CHOP Null (null) — パススルーの null です（チャンネルストリームへの安定した名前付きタップ）。 | `input` (+4 optional) |
| `chop_vector` | CHOP Vector (vector) — チャンネルの三つ組に対するベクトル演算（magnitude/normalize/dot/cross/project/...）です。 | `input` (+11 optional) |
| `chop_attribute` | CHOP Attribute (attribute) — チャンネル上のトランスフォームアトリビュート（rotation order / slerp）を管理します。 | `input` (+6 optional) |
| `chop_copy` | CHOP Copy (copy) — input 1 の各トリガーサンプルで input 0 をスタンプします。 | `input` (+7 optional) |
| `chop_shuffle` | CHOP Shuffle (shuffle) — 入力チャンネルを並べ替え/分割/シーケンス化します。 | `input` (+6 optional) |
| `chop_reorder` | CHOP Reorder (reorder) — 数値 / 文字パターンでチャンネルを並べ替えます。 | `input` (+10 optional) |
| `chop_rename` | CHOP Rename (rename) — パターンでチャンネルをリネームします。 | `input` (+7 optional) |
| `chop_delete` | CHOP Delete (delete) — 名前または番号でチャンネルを削除します。 | `input` (+12 optional) |
| `chop_switch` | CHOP Switch (switch) — インデックスで選択した接続入力のいずれかをパススルーします。 | `input` (+9 optional) |
| `chop_layer` | CHOP Layer (layer) — 接続された入力をレイヤーごとのウェイトでレイヤーします（active layer がベースを選択）。 | `input` (+8 optional) |
| `chop_composite` | CHOP Composite (comp) — 接続された入力を合成します（加算的な rise/peak/release）。 | `input` (+18 optional) |
| `chop_trigger` | CHOP Trigger (trigger) — 入力チャンネルによってトリガーされる ADSR 風のエンベロープを生成します。 | `input` (+16 optional) |
| `chop_footplant` | CHOP Foot Plant (footplant) — 歩行アニメーションの足の接地を検出+ロックし、スライドを解消します。 | `input` (+11 optional) |
| `chop_iksolver` | CHOP IK Solver (iksolver) — エンドアフェクターに到達するようボーンチェーンを解きます。 | `input` (+11 optional) |
| `chop_inversekin` | CHOP Inverse Kinematics (inversekin) — OBJ ボーンパスで駆動されるクラシックなボーンチェーン IK ソルバーです。 | 11 optional |
| `chop_transform_chain` | CHOP Transform Chain (transformchain) — トランスフォームのチェーンを出力チャンネルに再合成します。 | `input` (+7 optional) |
| `chop_export_transforms` | CHOP Export Transforms (exporttransforms) — トランスフォームチャンネルを OBJ ノードパラメータにマッピングします。 | `input` (+6 optional) |
| `chop_extract_bone_transforms` | CHOP Extract Bone Transforms (extractbonetransforms) — KineFX スケルトンのボーントランスフォームをチャンネルに読み込みます。 | 10 optional |
| `chop_extract_pose_drivers` | CHOP Extract Pose Drivers (extractposedrivers) — pose-space デフォーマーに供給するドライバーチャンネル（ジョイントの xform / パラメータ）を抽出します。 | 9 optional |
| `chop_blendpose` | CHOP Blend Pose (blendpose) — ドライバー値によってサンプルポーズをブレンドする pose-space 補間（RBF / hyperplane）です。 | `input` (+13 optional) |
| `chop_stashpose` | CHOP Stash Pose (stashpose) — pose-space ワークフロー用に、現在のポーズを静的な基準ポーズとしてスタッシュします。 | `input` (+5 optional) |

### Crowd

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `agent_source` | Crowd Agent (agent SOP) — エージェントプリミティブを作成/インポートします。input=scene（/obj ボーンサブネット）、disk（エージェントキャッシュディレクトリ）、fbx または usd。 | 16 optional |
| `agent_look_at` | Crowd Agent Look At (agentlookat::3.0) — エージェントの頭/眼のジョイントをターゲットに向けます。input0 = エージェント、input1 = ターゲットポイント（target_type=points）。 | `agents` (+19 optional) |
| `agent_terrain_adaptation` | Crowd Agent Terrain Adaptation (agentterrainadaptation::3.0) — DOP クラウドマイクロソルバーです。エージェントを地形に合わせて foot-locking + hip-adjust します。 | 17 optional |
| `agent_terrain_projection` | Crowd Agent Terrain Projection (agentterrainprojection) — エージェントのパーティクル/足を地形サーフェスに投影する DOP クラウドマイクロソルバーです。 | 14 optional |
| `agent_look_at_apply` | Crowd Agent Look At Apply (agentlookatapply::3.0) — 各シムステップでエージェントに頭/眼の look-at ターゲティングを適用する DOP クラウドマイクロソルバーです。 | 14 optional |
| `agent_clip_layer` | Crowd Agent Clip Layer (agentcliplayer) — エージェントにアニメーションクリップをレイヤー/ブレンドする DOP クラウドマイクロソルバーです。 | 15 optional |
| `agent_arcing_clip_layer` | Crowd Agent Arcing Clip Layer (agentarcingcliplayer) — エージェントに arcing/turning クリップをレイヤーする DOP クラウドマイクロソルバーです。 | 6 optional |
| `crowd_fuzzy_logic` | Crowd Fuzzy Logic (crowdfuzzylogic) — トリガー入力をファジー論理で組み合わせてトリガーアトリビュートにする DOP ノードです。 | 7 optional |
| `crowd_object` | Crowd Object (crowdobject) — クラウドシムでエージェントの群衆を保持する DOP オブジェクトです。 | 16 optional |
| `crowd_state` | Crowd State (crowdstate::3.0) — クラウドステートマシン内の名前付き挙動ステート（クリップ割り当て、gait、ragdoll モード）です。 | 13 optional |
| `agent_clip` | KineFX Agent Clip (agentclip::2.0) — モーションソースを名前付きクリップとしてエージェントプリミティブにベイクします。input0 = エージェント、input1 = MotionClip（source=sop/chop）。 | `agents` (+16 optional) |
| `crowd_trigger` | KineFX Crowd Trigger (crowdtrigger::2.0) — エージェントごとの条件（proximity/attribute/speed/distance/...）を評価し、トリガーアトリビュートを書き込みます。 | 19 optional |
| `crowd_trigger_logic` | KineFX Crowd Trigger Logic (crowdtriggerlogic::2.0) — 最大 2 つのトリガーストリームをブーリアン演算で組み合わせ、トリガーアトリビュートを書き込みます。 | 7 optional |
| `crowd_transition` | KineFX Crowd Transition (crowdtransition::3.0) — トリガーで発火する 2 つのクラウドステート間のトランジションを定義します。 | `input` (+17 optional) |
| `crowd_sop_import` | KineFX Crowd SOP Import (sopcrowdimport) — SOP クラウド（エージェントプリミティブ）を UsdSkel キャラクターとして USD ステージにインポートします。sop_path = エージェントを保持する SOP。 | `sop_path` (+7 optional) |
| `crowd_render_procedural` | KineFX Crowd Render Procedural (houdinicrowdprocedural) — レンダー時（Karma）のクラウド遅延ロードプロシージャルを設定し、エージェントをベイクせずレンダー時に展開させます。input（オプション）= クラウドを含む LOP ステージ。 | 13 optional |
| `bake_skinning` | KineFX Bake Skinning (bakeskinning) — 入力ステージ上の UsdSkel スキニングをデフォーム済みのポイント位置にベイクダウンします（crowd_sop_import 後のクラウドレンダー準備）。input（必須）= スキニング済みキャラクターを含む LOP ステージ。 | `input` (+1 optional) |
| `agent_channels` | KineFX Agent Channels (agent CHOP) — エージェントプリミティブのクリップまたはポーズのトランスフォームを CHOP トラックに評価します（クラウドアニメーションからリグ/ライト/オブジェクトを駆動）。sop_path = エージェントを保持する SOP。 | `sop_path` (+13 optional) |
| `agent_camera` | KineFX Agent Cam (agentcam) — クラウドエージェント自身のカメラ定義で駆動される /obj カメラです（エージェントの視点でレンダリング）。agent_source = エージェントを保持する SOP。 | 9 optional |
| `agent_clip_properties` | Crowd Agent Clip Properties (agentclipproperties) — エージェントのクリップカタログにクリップごとのメタデータ（フレーム範囲、サンプル単位、プレビュークリップ）を付与します。input0 = エージェント。 | `agents` (+5 optional) |
| `agent_clip_transition_graph` | Crowd Agent Clip Transition Graph (agentcliptransitiongraph) — エージェントのクリップ間トランジションブレンドを計算します。input0 = エージェント、input1 = 既存のトランジショングラフ、input2 = クリッププロパティ。 | `agents` (+8 optional) |
| `agent_collision_layer` | Crowd Agent Collision Layer (agentcollisionlayer) — ragdoll/bullet の衝突シェイプ用に、エージェントに衝突レイヤーを構築/マークします。input0 = エージェント。 | `agents` (+9 optional) |
| `agent_configure_joints` | Crowd Agent Configure Joints (agentconfigurejoints) — エージェントにジョイントごとの ragdoll 制限とガイド表示を設定します。input0 = エージェント。 | `agents` (+4 optional) |
| `agent_constraint_network` | Crowd Agent Constraint Network (agentconstraintnetwork) — エージェント用の ragdoll コンストレイントネットワーク（softness / ERP / CFM / bias 調整）を構築します。input0 = エージェント。 | `agents` (+12 optional) |
| `agent_definition_cache` | Crowd Agent Definition Cache (agentdefinitioncache) — キャッシュされたエージェント定義（rig/layers/shapes/clips/metadata）を読み込みます。 | 19 optional |
| `agent_edit` | Crowd Agent Edit (agentedit) — エージェントの current/collision レイヤー、現在のクリップ、クリップ時間を上書きします。input0 = エージェント。 | `agents` (+7 optional) |
| `agent_layer` | Crowd Agent Layer (agentlayer::2.0) — エージェントにシェイプレイヤーを追加/割り当て、current および collision レイヤーを設定します。input0 = エージェント、input1 = シェイプジオメトリ、input2 = キャプチャポーズ。 | `agents` (+17 optional) |
| `agent_metadata` | Crowd Agent Metadata (agentmetadata) — エージェント上の型付きメタデータ辞書を読み取り/マージ/設定します。input0 = エージェント。 | `agents` (+10 optional) |
| `agent_prep` | Crowd Agent Prep (agentprep::3.0) — クラウドシム用にエージェントを準備します（レストクリップ、リンブ設定、クリップ読み込み）。input0 = エージェント。cachedir + clippaths は作業ディレクトリ内に制限されます。create-chopnet/reload/save ボタンは決して押されません。 | `agents` (+11 optional) |
| `agent_proxy` | Crowd Agent Proxy (agentproxy) — 高速なクラウドプレビュー用に、エージェントポイントのビューポートプロキシ表示（LOD / id / color）を設定します。input0 = エージェントプリミティブを保持するポイント。 | `agents` (+6 optional) |
| `agent_relationship` | Crowd Agent Relationship (agentrelationship) — 子エージェントを親エージェント（オプションで特定のジョイント）に、position/rotation/all コンストレイントで親子付けします。input0 = 親エージェント、input1 = 子エージェント。 | `agents` (+10 optional) |
| `agent_transform_group` | Crowd Agent Transform Group (agenttransformgroup) — 加重デフォーメーション/ブレンド用に、エージェント上の名前付きトランスフォーム（ジョイント）グループを定義します。input0 = エージェント。 | `agents` (+10 optional) |
| `agent_unpack` | Crowd Agent Unpack (agentunpack) — エージェントプリミティブを、その基となるジオメトリ（deformed \| rest \| joints \| skeleton \| motionclips）にアンパックします。input0 = エージェント。 | `agents` (+15 optional) |
| `agent_vellum_unpack` | Crowd Agent Vellum Unpack (agentvellumunpack) — クロス/ソフトボディのクラウドセットアップ用に、エージェントをシム（Vellum）+ レストジオメトリにアンパックします。input0 = エージェント。 | `agents` (+16 optional) |
| `crowd_assign_layers` | Crowd Assign Layers (crowdassignlayers) — エージェント群の current & collision レイヤーを group / layer-pattern / percentage で割り当て/ランダム化します。input0 = エージェント。 | `agents` (+13 optional) |
| `crowd_motion_path` | Crowd Motion Path (crowdmotionpath) — 各エージェントに割り当てられたクリップ（またはキャッシュされたシム）をフレーム範囲にわたって評価し、クラウド用の編集可能なモーションパスカーブを生成します。input0 = クラウド（エージェントプリムを保持するポイント）。 | `agents` (+15 optional) |
| `crowd_motion_path_apply_relationship` | Crowd Motion Path Apply Relationship (crowdmotionpathapplyrel) — エージェントの親子関係をモーションパスに適用します。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+3 optional) |
| `crowd_motion_path_arcing_layer` | Crowd Motion Path Arcing Layer (crowdmotionpatharcinglayer) — 旋回レートに基づいてターン（arcing）クリップをモーションパスにレイヤーします。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+11 optional) |
| `crowd_motion_path_avoid` | Crowd Motion Path Avoid (crowdmotionpathavoid) — 衝突、隣接エージェント、障害物を避けるようモーションパスをステアリングします。input0 = モーションパス、input1 = エージェント（オプション）、input2 = 障害物（オプション）。 | `motion_paths` (+18 optional) |
| `crowd_motion_path_edit` | Crowd Motion Path Edit (crowdmotionpathedit) — モーションパスの pin-weight / scale-adjustment 編集です（非インタラクティブなデータ制御）。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+6 optional) |
| `crowd_motion_path_edit_core` | Crowd Motion Path Edit Core (crowdmotionpatheditcore) — モーションパス編集のデータコアです。pin-weight / scale-adjustment アトリビュートをモーションパスに適用します。input0 = モーションパス。 | `motion_paths` (+9 optional) |
| `crowd_motion_path_evaluate` | Crowd Motion Path Evaluate (crowdmotionpathevaluate) — クラウドのモーションパスを指定フレームでサンプリングし、ポージング済みのクラウドポイントを生成します。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+3 optional) |
| `crowd_motion_path_evaluate_core` | Crowd Motion Path Evaluate Core (crowdmotionpathevaluatecore) — モーションパス評価のデータコアです。指定時刻でモーションパスからエージェントをポージングします。 | `agents` (+4 optional) |
| `crowd_motion_path_follow` | Crowd Motion Path Follow (crowdmotionpathfollow) — ガイドカーブに追従するようモーションパスをデフォームします。input0 = モーションパス、input1 = エージェント（オプション）、input2 = 追従するカーブ（オプション）。 | `motion_paths` (+14 optional) |
| `crowd_motion_path_layer` | Crowd Motion Path Layer (crowdmotionpathlayer) — トリガーされたとき（トリガーグループ経由で）アニメーションクリップをモーションパスにレイヤーします。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+19 optional) |
| `crowd_motion_path_retime` | Crowd Motion Path Retime (crowdmotionpathretime) — モーションパスのフレーム範囲と再生速度をリタイム/クリップします。input0 = モーションパス、input1 = エージェント（オプション）。 | `motion_paths` (+8 optional) |
| `crowd_motion_path_transition` | Crowd Motion Path Transition (crowdmotionpathtransition) — トリガーされたとき、モーションパスを現在のクリップから新しいクリップにトランジションします。input0 = モーションパス、input1 = エージェント。 | `motion_paths` (+19 optional) |
| `crowd_source` | Crowd Source (crowdsource::3.0) — クラウドシムの種となるクラウドポイントストリーム（隊列グリッドまたはスキャッター）を生成します。各ポイントは初期ステート / クリップ / heading を持つエージェントを生成します。 | 27 optional |
| `crowd_motion_path_trigger` | Crowd Motion Path Trigger (crowdmotionpathtrigger) — クラウドのモーションパスに沿ってトリガー条件（time / bounds / object-distance / raycast / neighbor-distance / clip）を評価し、トランジションが使用する名前付きトリガーを書き込みます。 | `motion_paths` (+29 optional) |
| `agent_animation_unpack` | Agent Animation Unpack (kinefx::agentanimationunpack) — エージェントのアニメーションを KineFX スケルトン `output` にアンパックします。pose / agent-clip pose / rest pose / motion clip / packed motion clips。 | `agents` (+14 optional) |
| `agent_character_unpack` | Agent Character Unpack (kinefx::agentcharacterunpack) — エージェントをその構成ジオメトリにアンパックします。output 0 = スキンシェイプ、output 1 = スケルトン、output 2 = キャプチャポーズ。 | `agents` (+15 optional) |
| `agent_from_rig` | Agent From Rig (kinefx::agentfromrig) — KineFX リグ/スケルトンを単一の Agent プリミティブに変換します（レストポーズ、クリップなし）。 | `rig` (+10 optional) |
| `agent_pose_from_rig` | Agent Pose From Rig (kinefx::agentposefromrig) — KineFX リグ/スケルトンのポーズからエージェントのポーズを駆動します（両方の入力が必須）。 | `agents`, `rig` (+7 optional) |
| `agent_transforms` | Crowd Agent Transforms (agenttransforms) — エージェントプリミティブのトランスフォーム行列を読み取るデータプロバイダー VOP です。 | 7 optional |
| `agent_transform_names` | Crowd Agent Transform Names (agenttransformnames) — エージェントのリグの順序付きトランスフォーム（ジョイント）名を読み取るデータプロバイダー VOP です。 | 6 optional |
| `agent_transform_count` | Crowd Agent Transform Count (agenttransformcount) — エージェントのリグ内のトランスフォーム（ジョイント）数を出力するデータプロバイダー VOP です。 | 6 optional |
| `agent_rig_find` | Crowd Agent Rig Find (agentrigfind) — エージェントのリグ内で名前付きジョイントのトランスフォームインデックスを返すデータプロバイダー VOP です。 | 7 optional |
| `agent_rig_children` | Crowd Agent Rig Children (agentrigchildren) — エージェントのリグ階層内でジョイントの子トランスフォームインデックスを返すデータプロバイダー VOP です。 | 7 optional |
| `agent_rig_parent` | Crowd Agent Rig Parent (agentrigparent) — エージェントのリグ階層内でジョイントの親トランスフォームインデックスを返すデータプロバイダー VOP です。 | 7 optional |
| `agent_clip_weights` | Crowd Agent Clip Weights (agentclipweights) — エージェントのアクティブなクリップごとのブレンドウェイトを読み取るデータプロバイダー VOP です。 | 6 optional |
| `agent_layers` | Crowd Agent Layers (agentlayers) — エージェント定義上のレイヤー名のリストを読み取るデータプロバイダー VOP です。 | 6 optional |
| `agent_layer_name` | Crowd Agent Layer Name (agentlayername) — エージェントのレイヤー名を解決するデータプロバイダー VOP です（例: current / collision レイヤー）。 | 7 optional |
| `agent_layer_bindings` | Crowd Agent Layer Bindings (agentlayerbindings) — 名前付きエージェントレイヤーの shape->transform バインディングを読み取るデータプロバイダー VOP です。 | 8 optional |
| `agent_layer_shapes` | Crowd Agent Layer Shapes (agentlayershapes) — 名前付きエージェントレイヤー内のシェイプ名を読み取るデータプロバイダー VOP です。オプションでシェイプタイプでフィルタします。 | 8 optional |
| `agent_convert_transforms` | Crowd Agent Convert Transforms (agentconverttransforms) — エージェントのトランスフォーム配列を空間間（例: local <-> world）で変換するデータプロバイダー VOP です。 | 7 optional |

### Muscle

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `franken_muscle` | Muscle Franken Muscle (frankenmuscle) — 単一のマッスルジオメトリ内に複数の `muscle_id` サブリージョンを割り当て、1 つのソリッドメッシュを複数の独立したマッスルとして振る舞わせます。 | `muscle` (+10 optional) |
| `franken_muscle_paint` | Muscle Franken Muscle Paint (frankenmusclepaint) — マッスルジオメトリ（input 0）上の `muscle_id` マスクのペイントフロントエンドです。 | `muscle` (+20 optional) |
| `muscle_id` | Muscle Muscle ID (muscleid) — 接続された各サーフェスクラスターにプリミティブごとの `muscle_id` name アトリビュートを割り当て、下流のマッスル SOP がマッスルを個別に扱えるようにします。 | `surface` (+8 optional) |
| `muscle_solidify` | Muscle Muscle Solidify (musclesolidify) — マッスル SURFACE をテトラ化してソリッドマッスル（`muscle_id` + `maxthickness` を保持）にし、プロパティ + シミュレーションに備えます。 | `surface` (+14 optional) |
| `muscle_properties` | Muscle Muscle Properties (muscleproperties) — マッスルごとのソリッドマテリアルプロパティ（shape/volume/damping/mass/fiber/tendon stiffness）を付与し、ソリッドマッスル上で `materialW` のファイバー方向フレームを計算します。 | `muscle` (+19 optional) |
| `muscle_properties_otis` | Muscle Muscle Properties OTIS (musclepropertiesotis) — Muscle Properties の OTIS ソルバー版です（OTIS のマッスル・組織シム用のマッスルごとのソリッドマテリアルプロパティ）。 | `muscle` (+19 optional) |
| `muscle_constraint_properties_fem` | Muscle Muscle Constraint Properties FEM (muscleconstraintpropertiesfem) — FEM マッスルソルバー用に、マッスルごとの CONSTRAINT プロパティ（end / muscle-to-muscle / muscle-to-bone の stiffness、damping、distance）を付与します。 | `muscle` (+13 optional) |
| `muscle_constraint_properties_otis` | Muscle Muscle Constraint Properties OTIS (muscleconstraintpropertiesotis) — マッスル CONSTRAINT プロパティ付与ノードの OTIS ソルバー版です（end / glue / muscle-to-muscle の stiffness + damping + distance）。 | `muscle` (+11 optional) |
| `muscle_constraint_properties_vellum` | Muscle Muscle Constraint Properties Vellum (muscleconstraintpropertiesvellum) — マッスル CONSTRAINT プロパティ付与ノードの Vellum ソルバー版です（end / muscle-to-muscle / muscle-to-bone の stiffness、damping、distance、compress、slide-rate）。 | `muscle` (+15 optional) |
| `muscle_auto_tension_lines` | Muscle Auto Tension Lines (muscleautotensionlines) — 各 `muscle_id` リージョンの長軸に沿ってテンションラインカーブを自動生成します（マッスルデフォーマーが屈曲する際のドライバー）。 | `muscle` (+5 optional) |
| `muscle_tension_lines` | Muscle Tension Lines (muscletensionlines) — テンションライン付与ノードです。マッスルを屈曲させるのに使うテンションラインを選択/編集し、対称性をサポートします。 | `muscle` (+8 optional) |
| `muscle_tension_lines_activate` | Muscle Tension Lines Activate (muscletensionlinesactivate) — テンションラインをアクティブ化/アニメーションします（グループごとの min/max アクティベーション、体をまたいだミラーアクティベーション）。 | `tension_lines` (+11 optional) |
| `muscle_deform` | Muscle Muscle Deform (muscledeform::2.0) — 現代的な準静的マッスルデフォーマーです。ファイバーの stiffness + tension でテンションラインに追従するようマッスルソリッドを解きます。 | `muscle`, `tension_lines`, `tension_lines_anim` (+13 optional) |
| `muscle_flex` | Muscle Muscle Flex (muscleflex::2.0) — ファイバースケールのブレンドによってテンションラインに沿ってマッスルを屈曲させます（高速でソルブなしの膨張）。 | `muscle` (+15 optional) |
| `muscle_preroll` | Muscle Muscle Preroll (musclepreroll) — レストポーズから hold + preroll のフレーム範囲にわたってマッスルデフォーメーションをプリロールし、ショット開始前にシムを落ち着かせます。 | `muscle` (+7 optional) |
| `muscle_merge` | Muscle Muscle Merge (musclemerge) — 最大 6 つのマッスルストリームを 1 つのマッスルシステムにマージします（`muscle_id` は区別したまま保持）。 | `muscle` (+6 optional) |
| `muscle_mirror` | Muscle Muscle Mirror (musclemirror) — 体の片側からもう一方へマッスルをミラーリングし、`muscle_id` をプレフィックス入れ替えでリネームします。 | `muscle` (+7 optional) |
| `muscle_deintersect` | Muscle Muscle Deintersect (muscledeintersect) — 重なり合うマッスルを押し離して相互貫入を止め、厚みオフセットまで広げます。 | `muscle` (+4 optional) |
| `muscle_adjust_volume` | Muscle Muscle Adjust Volume (muscleadjustvolume) — 法線 + 接線に沿ってマッスルのボリュームを拡大/縮小します。オプションでスキンとの衝突解決を行います。 | `muscle` (+15 optional) |
| `muscle_slide_constraint` | Muscle Muscle Slide Constraint (muscleslideconstraint) — マッスルが隣接マッスル / ボーンの上をスライドしつつストレッチに抵抗できるようにするスライディングコンストレイントを構築します。 | `muscle` (+12 optional) |
| `muscle_tpose` | Muscle Muscle T-Pose (muscletpose) — マッスルのレスト（T ポーズ）シェイプを名前付きアトリビュートに保存/復元し、下流のデフォーマーが安定した基準ポーズを持てるようにします。 | `muscle` (+5 optional) |
| `otis_configure_muscle_tissue` | Muscle OTIS Configure Muscle and Tissue (otisconfiguremuscleandtissue) — マッスル + 組織のジオメトリとコンストレイントを、OTIS ソルバーが消費するペイロードに組み立てます（muscle-end / glue / tissue-to-bone コンストレイント、テト品質）。 | `muscle` (+19 optional) |
| `tissue_solidify` | Muscle Tissue Solidify (tissuesolidify::2.0) — スキン/マッスルサーフェスの下に、指定した厚みのテトラ化された組織（脂肪/筋膜）シェルを構築します。 | `surface` (+16 optional) |
| `tissue_solidify_otis` | Muscle Tissue Solidify OTIS (tissuesolidifyotis) — OTIS ソルバー版です。EXTERIOR のスキンと内側のシュリンクラップされたサーフェスの間に組織ボリュームを構築します。 | `skin` (+14 optional) |
| `tissue_properties` | Muscle Tissue Properties (tissueproperties) — プリセットまたは明示的な値から組織のマテリアルプロパティ（surface + solid + sliding の stiffness/damping/mass、rest scale）を付与します。オプションでマスクします。 | `tissue` (+18 optional) |
| `tissue_properties_otis` | Muscle Tissue Properties OTIS (tissuepropertiesotis) — Tissue Properties の OTIS ソルバー版です（core + shell の solid stiffness/damping/mass、tissue-to-muscle / tissue-to-bone stiffness）。 | `tissue` (+20 optional) |
| `muscle_paint` | Muscle Muscle Paint (musclepaint) — マッスルジオメトリ（input 0）上のマッスルアトリビュート / マスクのペイントフロントエンドです。 | `muscle` (+18 optional) |

### VEX (validated safe-VEX)

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `set_attrib_expr` | 検証済みVEX（safe-VEX）のアトリビュートスニペットを保持するラングルを介して、ジオメトリアトリビュート上で安全な VEX スニペットを実行します — ブリッジで唯一のコードテキストの経路です。 | `outputs`, `code` (+8 optional) |

### ML / ONNX inference

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `onnx_inference` | 制限された ONNX テンソルグラフモデルを、ポイントアトリビュートまたはボリュームフィールド上で実行します — クラウドやボリュームの学習ベースの super-res / denoise / セグメンテーションです。 | `input`, `modelfile`, `input_name`, `input_type` (+8 optional) |
| `ml_regression` | Labeled-Examples 入力からアトリビュート回帰をインラインで学習 + 推論します — ポイントクラウドやハイトフィールド上での学習ベースの mask/label/value 予測です。 | `input`, `examples`, `method` (+6 optional) |
| `pca` | ポイント/ボリュームアトリビュートに対する主成分分析（PCA）です — 特徴量の圧縮、シェイプ空間解析、および ml_regression の前処理フロントエンドです。 | `input` (+6 optional) |
| `ml_volume_upres` | 学習ベースのボリュメトリック超解像です — 粗くシミュレーションして詳細をアップレスします（pyro/fluid コンテンツの経路）。modelfile は制限された .onnx です。ここでは設定のみでクックはしません（ハッシュ固定されたファイルで下流のクック時に解決）。 | `input`, `modelfile` (+5 optional) |
| `acquire_model` | ML ツール用の ONNX モデルを、HuggingFace ホスト許可リストから <workdir>/models/ にダウンロードし、固定された sha256 に対して検証します。 | `repo`, `file`, `sha256` (+2 optional) |
| `ml_example` | Input Component（input 0）と Target Component（input 1、必須）を 1 つの教師あり学習 EXAMPLE（ml_example）にペアリングします — ML データセットの原子単位（features -> targets）です。 | `input`, `target` (+5 optional) |
| `ml_extract_example` | Examples ストリーム（ml_extractexample）から単一の学習サンプル（インデックス指定）を取り出します — 1 サンプルを検査/プレビューします。 | `input` (+3 optional) |
| `ml_attrib_generate` | プロトタイプ上にランダム化されたアトリビュート値を合成します（ml_attribgenerate）— 制御されたランダム入力で学習セットをデータ拡張します。 | `input` (+6 optional) |
| `ml_pose_generate` | Pose Prototype からランダム化されたスケルトンポーズをサンプリングします（ml_posegenerate）— pose-space / ML デフォーマー用の学習データ生成器です。 | `input` (+4 optional) |
| `ml_pose_serialize` | スケルトンポーズをシリアルなポイント ATTRIBUTE に平坦化します（ml_poseserialize）— リグポーズを ML モデルが消費する固定長の特徴ベクトルに変換します。 | `input` (+9 optional) |
| `ml_example_partition` | Examples ストリームを max_part_size 以下のパートに分割します（ml_examplepartition）— 大きな学習セットを扱いやすいチャンクにバッチ分割します。 | `input` (+2 optional) |
| `ml_deform` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）: 学習ベースのキャラクターデフォーマー（ml_deform）を構築します — 学習済み（TRAINED）モデルを適用し、スケルトンポーズで駆動してスキンをデフォームします。 | `input`, `modelfile` (+7 optional) |
### Copernicus / COP

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `cop_constant` | COPジェネレーター：定数値の画像レイヤー（Constant）。 | 4 optional |
| `cop_fractal_noise` | COPジェネレーター：フラクタルノイズ（Fractal Noise） — 中核となるプロシージャルなテクスチャソース。noise_type、距離メトリック、振幅、エレメントサイズ、オクターブ、ラキュナリティ、ラフネス、コントラスト。 | 9 optional |
| `cop_ramp` | COPジェネレーター：線形／放射状のグラデーション（Ramp）。ramp_type、サイクル数、位相、範囲外メソッド。 | 5 optional |
| `cop_remap` | COPフィルター：レイヤーの値域をリマップ（Remap）。op=remap は input_min/max を output_min/max へ範囲外メソッド付きでマッピングし、op=threshold は threshold＋width＋side を使用します。 | `input` (+10 optional) |
| `cop_invert` | COPフィルター：レイヤーを反転（Invert）。method：complement（1-x）、negate（-x）、reciprocal（1/x）。 | `input` (+2 optional) |
| `cop_equalize` | COPフィルター：レイヤーの値域を伸長／シフトしてコントラストを正規化（Equalize）。mode、fit_method、輝度タイプ、黒／白ポイント、目標平均値。 | `input` (+7 optional) |
| `cop_blend` | COPフィルター：2つのレイヤーをコンポジット（Blend）。 | `input`, `fg` (+3 optional) |
| `cop_bright` | COPフィルター：明度／レベル調整（Bright）。brightness は乗算、shift は加算。 | `input` (+3 optional) |
| `cop_hsv` | COPフィルター：色相／彩度／明度の調整、またはRGB↔HSV変換（HSV Adjust）。op、hue_shift、sat_scale、sat_shift、val_scale、val_shift。 | `input` (+7 optional) |
| `cop_glow` | COPフィルター：明るい領域からのブルーム／グロー（Glow）。threshold、明度ゲイン、ブラーサイズ、filter（box/gaussian）、units（image/pixels）。 | `input` (+7 optional) |
| `cop_quantize` | COPフィルター：レイヤーを離散的なステップにポスタライズ（Quantize）。method（width/segments）、segments 数または width、丸め方。 | `input` (+5 optional) |
| `cop_blur` | COPフィルター：レイヤーをブラー（Blur）。size（半径）、filter（box/gaussian）、units（image/pixels）。 | `input` (+5 optional) |
| `cop_sdf_shape` | COPジェネレーター：符号付き距離場（SDF）による2Dシェイプ（SDF Shape） — 円、矩形、星、三角形、スクワークル、その他多数。shape_class でファミリーを選び、`shape` がシェイプ名、scale がサイズ、translate＋rotate が位置を決めます。 | 6 optional |
| `cop_sdf_blend` | COPフィルター：2つのSDFレイヤーを結合（SDF Blend）。 | `input`, `b` (+6 optional) |
| `cop_sdf_to_mono` | COPフィルター：SDFをモノレイヤーにラスタライズ（SDF To Mono） — fill 値、背景値、オプションのアウトライン（width＋inside/outside/center）、アンチエイリアス。 | `input` (+7 optional) |
| `cop_sdf_to_rgb` | COPフィルター：SDFをカラーレイヤーにラスタライズ（SDF To RGB） — オプションのアウトライン（width＋inside/outside/center）、アンチエイリアス、iso オフセット。 | `input` (+6 optional) |
| `cop_sdf_adjust` | COPフィルター：SDFを調整（SDF Adjust） — iso_offset がフィールドを膨張／収縮させ、onion が中空のシェルを作り、abs で片側化、invert で内外を入れ替えます。 | `input` (+5 optional) |
| `cop_id_to_sdf` | COPフィルター：ID／ラベルレイヤーからSDFを構築（ID To SDF） — 最も近いID境界までの距離。invert が符号を反転、iterations が伝播を制御、tile_size がブロックサイズ。 | `input` (+4 optional) |
| `cop_median` | COPフィルター：メディアンフィルター（Median） — エッジを保ったままソルト＆ペッパーノイズ／スペックルを除去。size = 3または5ピクセル、mask で結果をミックス。 | `input` (+3 optional) |
| `cop_streak_blur` | COPフィルター：直線に沿った方向性／モーションブラー（Streak Blur）。dir_type（angle/coord）、angle、length、units、mode（on/min/max の合成）。 | `input` (+8 optional) |
| `cop_kuwahara` | COPフィルター：Kuwaharaフィルター（Kuwahara Filter） — エッジ保存型の絵画調スムージング。radius（領域サイズ、ピクセル）、輝度タイプ、blend、separation。 | `input` (+6 optional) |
| `cop_compare` | COPフィルター：レイヤーを値または2つ目のレイヤーと比較し、0/1のマスクを出力（Compare）。 | `input` (+7 optional) |
| `cop_edge_detect` | COPフィルター：エッジ検出（Edge Detect）。preblur が検出前にソフト化、normalize が出力をスケール、low/high の閾値が弱い／強いエッジをゲートします。method＋mode は整数のセレクター。 | `input` (+7 optional) |
| `cop_sharpen` | COPフィルター：シャープ化（Sharpen） — アンシャープマスクによりディテールを強調。amplitude、gain、threshold、size、units（image/pixels）。 | `input` (+6 optional) |
| `cop_tile_pattern` | COPジェネレーター：レンガ／タイルパターン（Tile Pattern） — stackbond、herringbone、basketweave、flemishbond など各種の組積レイアウト。pattern がレイアウトを選択、mode（seamless/tilecount/tilesize）、tiled_size がスケール。 | 4 optional |
| `cop_sequence_blend` | COPフィルター：時間的シーケンスにわたってブレンド（Sequence Blend） — モーショントレイル／フレーム平均。blend = ミックス量、invert で反転。 | `input` (+3 optional) |
| `cop_wipe` | COPフィルター：2つのレイヤー間のトランジション／ワイプ（Wipe）。 | `input`, `b` (+6 optional) |
| `cop_chromatic_aberration` | COPフィルター：レンズの色収差（Chromatic Aberration) — チャンネルごとのスケール／回転でR/G/Bをフリンジ化。r_scale/g_scale/b_scale、overall_scale、r_angle/g_angle/b_angle、filter。 | `input` (+9 optional) |
| `cop_convolve` | COPフィルター：3x3の畳み込みカーネル（Convolve） — シャープ化／エンボス／エッジ／カスタム。 | `input` (+7 optional) |
| `cop_distort` | COPフィルター：レイヤーをワープ（Distort） — ある角度に沿ってピクセルを押し出す（均一）か、`distortion`（input 1）として配線した歪みベクトルレイヤーで押し出します。angle、scale、dir_type、filter、border。 | `input` (+7 optional) |
| `cop_derivative` | COPフィルター：画像の勾配／傾斜（Derivative） — レイヤーの変化率で、法線／エッジ／レリーフ用。angle、scale、offset、difference_mode（central/forward/diagonal）。 | `input` (+5 optional) |
| `cop_segment_connectivity` | COPフィルター：連結領域に一意のIDでラベル付け（Segment By Connectivity） — id_to_sdf ／領域ごと処理のフロントエンド。connectivity（閾値に対して below/above/at/levels）、threshold、offset、collapse。 | `input` (+5 optional) |
| `cop_segment_value` | COPフィルター：レイヤーをラベル付きの値帯に量子化（Segment By Value) — method（width または segments）、width または segment 数、min/max の範囲。 | `input` (+6 optional) |
| `cop_smooth_fill` | COPフィルター：領域を滑らかに充填／拡張（Smooth Fill） — ソース値を fill_area へ拡散させます（インペイント／境界の拡張）。 | `input`, `fill_area` (+4 optional) |
| `cop_fill` | COPフィルター：レイヤーをフラッドフィル（Fill） — 値／サンプルで置き換え。source（value/sample/first/last）、color（充填値）、id。 | `input` (+4 optional) |
| `cop_feather` | COPフィルター：マスクエッジをフェザー／ソフト化（Feather） — direction（diamond/square/oct/circle）、decay_mode（unitdist/decay）、decay、unit_distance。outside は外側へフェザーします。 | `input` (+6 optional) |
| `cop_light` | COPフィルター：法線レイヤーでレイヤーをシェーディング（Light）。 | `input`, `normals` (+4 optional) |
| `cop_bokeh` | COPフィルター：ボケ／被写界深度ブラー（Bokeh） — radius、gain（ハイライトのブースト）、resolution、フィルターカーネル、normalize。 | `input` (+6 optional) |
| `cop_dilate_erode` | COPフィルター：モルフォロジーの膨張／収縮（Dilate Erode） — 正の radius で明るい領域を成長、負で収縮、soft_edge でフェザー、fill で穴を閉じます。 | `input` (+5 optional) |
| `cop_channel_extract` | COPフィルター：単一チャンネルをモノレイヤーへ抽出（Channel Extract）。channel = インデックス（0=R,1=G,2=B,3=A）。 | `input` (+2 optional) |
| `cop_channel_swap` | COPフィルター：チャンネルをシャッフル（Channel Swap） — 各出力チャンネルを任意のソースチャンネルまたは0／1に設定。 | `input` (+5 optional) |
| `cop_mono_to_rgb` | COPフィルター：値域を介してモノレイヤーをRGBへマッピング（Mono To RGB）。input_min/max -> output_min/max、method（clamp/repeat）。 | `input` (+6 optional) |
| `cop_mono_to_rgba` | COPフィルター：レイヤーをRGBAへ昇格（Mono To RGBA） — alpha_mode は extend（値をコピー）または value（定数 alpha_value）。 | `input` (+3 optional) |
| `cop_premult` | COPフィルター：アルファの乗算済み化／乗算解除（Premult）。op = mult（乗算済み化）または divide（乗算解除）。 | `input` (+2 optional) |
| `cop_crop` | COPフィルター：レイヤーをクロップ（Crop）。crop_min/crop_max = [x,y] のコーナー（image 単位 0..1）、mode（data/both/display）、境界処理。 | `input` (+5 optional) |
| `cop_tonemap` | COPフィルター：HDRを表示域にトーンマップ（Tonemap）。operator = インデックス 0..5（Reinhard／Hable／ACES系カーブ）、exposure が事前ゲインを調整。 | `input` (+3 optional) |
| `cop_contrast` | COPフィルター：コントラスト調整（Contrast） — 中心ピボットを軸としたコントラストの強度。 | `input` (+3 optional) |
| `cop_gamma` | COPフィルター：ガンマ補正（Gamma） — gamma 値、オプションで invert。 | `input` (+3 optional) |
| `cop_transform` | COPフィルター：レイヤーを2D/3D変換（Transform）。translate/rotate/scale_xyz/shear/pivot（各 [x,y,z]）、uniform scale、transform＋rotation の順序、invert、境界処理と再構築フィルター。 | `input` (+12 optional) |
| `cop_color_correct` | COPフィルター：階調域のカラーグレーディング（Color Correct）。 | `input` (+10 optional) |
| `cop_checkerboard` | COPジェネレーター：チェッカーボードのテストパターン（Checkerboard）。rows/cols の分割数、even/odd のタイル色 [r,g,b]、translate/tile_size/bias（[x,y]）。 | 8 optional |
| `cop_clamp` | COPフィルター：値を下限／上限にクランプ（Clamp）。 | `input` (+5 optional) |
| `cop_channel_join` | COPコンバイナー：個別のモノレイヤーを1つのRGB/RGBAレイヤーにマージ（Channel Join）。 | `inputs` (+3 optional) |
| `cop_chroma_key` | COPフィルター：HSV範囲によるグリーン／ブルースクリーンのキーヤー（Chroma Key） -> マット。hue_circle [4]（色相／彩度の中心＋幅）、lum_range [min,max]、hue/sat/lum の rolloff によるソフトエッジ、interpolation（rolloff 関数 0..4）、preview＋preview_color [r,g,b]、premult（入力をマットで乗算）。 | `input` (+10 optional) |
| `cop_histogram` | COPフィルター：入力の値ヒストグラムを画像としてレンダリング（Histogram）。mode（colorbar/separatebar/graph）、buckets、min/max の範囲、outside（discard/clamp）、scale。set_res＋res [w,h] で出力解像度を上書き。 | `input` (+9 optional) |
| `cop_vignette` | COPフィルター：フレーム端に向けて暗く／明るくする（Vignette）。shape（round/rectangle/blend）、brightness、circle_radius/circle_scale [x,y]、blend 量、rect_size [x,y]/rect_roundness、center [x,y]、blur、mask。 | `input` (+11 optional) |
| `cop_height_to_normal` | COPフィルター：モノの高さレイヤーから法線マップレイヤーを導出（Height to Normal） -- レリーフシェーディング用に cop_light の `normals` へ供給。normal_type（signed/offset）、scale（高さゲイン）、read_outside、kernel（微分距離）。 | `input` (+5 optional) |
| `cop_mirror` | COPフィルター：1つ以上の平面でレイヤーをミラー／万華鏡化（Mirror）。mode 0 = カスタム平面（angle0/offset0/flip0）、1 = 個数とオフセット（num_planes＋angle/offset）、flip で反射。 | `input` (+9 optional) |
| `cop_average` | COPコンバイナー：複数の入力レイヤーを1つの演算で結合（Average）。operation（add/average/multiply/min/max/over）、`inputs` = 0..n に配線したCOPノードパス、signature = 出力レイヤータイプ。 | `inputs` (+3 optional) |
| `cop_worley_noise` | COPジェネレーター：セルラー／Worley（Voronoi）ノイズ（Worley Noise) -- cop_fractal_noise を補完。element_size（セルサイズ）、jitter、lattice（grid/hex）、metric、offset [x,y]、tiled＋tile_size [x,y]、post の bias/gain/contrast（自動有効化）、complement。 | 12 optional |
| `cop_julia` | COPジェネレーター：ジュリア集合フラクタル（Julia）。real/imag = ジュリア定数、escape_radius＋max_iter で発散判定を制御、scale [x,y]。 | 7 optional |
| `cop_chladni` | COPジェネレーター：クラドニ／サイマティクスの定在波節パターン（Chladni）。output（lines/abs/sdf）、threshold＋width（節線モード）、amp/amp_ratio、freq/freq_ratio、tile_size [x,y]。 | 9 optional |
| `cop_bubble_noise` | COPジェネレーター：バブル／セルラーのフラクタルノイズ（Bubble Noise）。amp/center、element_size、phase [4]、offset [x,y]、tile_size [x,y]、max_octaves、lacunarity、roughness、distort、stretch [x,y]、fold、post の bias（自動有効化）。 | 14 optional |
| `cop_crystal_noise` | COPジェネレーター：ファセット状の結晶質なWorley由来ノイズ（Crystal Noise）。amp/center/contrast、metric、jitter、element_size、secondary＋metric2、flatten_faces、tiled＋tile_size [x,y]、use_3d。 | 14 optional |
| `cop_phasor_noise` | COPジェネレーター：phasor／Gabor のプロシージャルな波＋ノイズのフィールド（Phasor Noise）。type（phasorwave/phasornoise/gabornoise/intensityfield）、wave_type（sine/rectangle/saw）、amp/center、element、wave_bias、blend、offset [x,y]、seed、kernels、rotation（uniform/varying）、use_3d。 | 14 optional |
| `cop_height_to_ao` | COPフィルター（地形レリーフ）：モノの高さレイヤーからアンビエントオクルージョンをベイク（Height to Ambient Occlusion）。height_scale、view_radius（レイ距離）、step_scale、ray_count、hemisphere。 | `input` (+6 optional) |
| `cop_height_to_shadow` | COPフィルター（地形レリーフ）：モノの高さレイヤー＋ライトプロファイルから投影シャドウマップを生成（Height to Shadow）。light_type（disk/sphere/directional）、coord_mode（spherical/cartesian）、azimuth/altitude/distance（spherical）または position [x,y,z]（cartesian）、radius、height_scale、view_radius、step_scale。 | `input` (+11 optional) |
| `cop_curvature` | COPフィルター（地形レリーフ）：法線／高さレイヤーから表面の曲率を算出（Curvature）。method（インデックス 0/1）、curvature_type（gaussian/mean/principal_max/principal_min）、output_type（インデックス 0/1/2）、normal_type（signed/offset）、prescale/postscale、kernel、read_outside、normalize＋min/max クランプ。 | `input` (+13 optional) |
| `cop_slope_dir` | COPフィルター（地形レリーフ）：モノの高さレイヤーから傾斜方向（アスペクト）フィールドを生成（Slope Direction）。angle（後段の回転）、scale（高さスケール調整）、read_outside、kernel。 | `input` (+5 optional) |
| `cop_resample` | COPフィルター：レイヤーをリサイズ／リサンプル（Resample）。size_control（res/aspect/pixel）、base_size（parm/input）、resolution [w,h]、aspect [x,y]＋aspect_preset、pixel_size、scale、fixed_side、filter（再構築）、stretch モード、reframe。 | `input` (+12 optional) |
| `cop_mono` | COPフィルター：チャンネルを単一のモノ／輝度レイヤーへ結合（Mono）。op（lum/ntsclum/hdtvlum/average/max/min/magnitude/hue/saturation/value/red/green/blue/comp4/custom）。`weight` [4] を与えると op=custom＋チャンネルごとのウェイトになり、normalize_weight。 | `input` (+4 optional) |
| `cop_hextile` | COPフィルター：六角形のシームレスなテクスチャタイリング（Hex Tile）。 | 11 optional |
| `cop_convert_normal` | COPフィルター：法線マップレイヤーをエンコーディング間で変換（Convert Normal）。conversion（tosigned -1..1 ／ tooffset 0..1）、normalize、offset [x,y,z]、scale [x,y,z]。 | `input` (+5 optional) |
| `cop_combine_normals` | COPコンバイナー：2つのタンジェント空間法線マップをレイヤー／ブレンド（Combine Normals）。 | `input`, `fg` (+4 optional) |
| `cop_edge_detect_normal` | COPフィルター：法線レイヤーの角度不連続からインク／アウトラインのエッジを生成（Edge Detect Normal）。tolerance、thickness_scale、weight_spread、blur、min_probe_radius。 | `input` (+6 optional) |
| `cop_edge_detect_depth` | COPフィルター：Z深度のステップからクリース／オクルージョンのエッジを生成（Edge Detect Depth）。tolerance、thickness_scale、weight_spread、blur、min_probe_radius。 | `input` (+6 optional) |
| `cop_edge_detect_contour` | COPフィルター：値の不連続からシルエット／コンターのエッジを生成（Edge Detect Contour）。tolerance、thickness_scale、weight_spread、blur、min_probe_radius。 | `input` (+6 optional) |
| `cop_swirl` | COPフィルター：スパイラル＋レンズバルジのデフォメーション（Swirl）。 | `input` (+14 optional) |
| `cop_pixelate` | COPフィルター：レイヤーをモザイク／ブロック量子化（Pixelate）。mode（インデックス 0/1）、units（image/pixels）、block_size または num_blocks [x,y]、offset [x,y]、mask。preblur＋preblur_size。 | `input` (+9 optional) |
| `cop_defocus` | COPフィルター：物理パラメーター化されたカメラのデフォーカス＋ボケ（Defocus）。 | `input`, `depth` (+12 optional) |
| `cop_flip` | COPフィルター：レイヤーをミラー（Flip）。horizontal（xflip）、vertical（yflip）、diagonal（flop）、mask。 | `input` (+5 optional) |
| `cop_polar_to_uv` | COPジェネレーター：極（角度、長さ）座標をUVレイヤーへ変換（Polar to UV）。angle_unit（rad/deg/tau）、angle、length。 | 4 optional |
| `cop_random_mono` | COPジェネレーター：ランダムなモノフィールド（Random Mono）。range_method（minmax/ramp/specific）、min/max、per_pixel、seed、time。 | 7 optional |
| `cop_random_rgb` | COPジェネレーター：ランダムなカラーフィールド（Random RGB）。range_method（minmax/ramp/specific）、color_model（rgb/hsv）、base_color [r,g,b]（ベースカラーを有効化）、チャンネルごとのランダム範囲 rand_r/g/b または rand_hue/sat/val（各 [min,max]）、per_pixel、seed。 | 12 optional |
| `cop_triplanar` | COPフィルター：テクスチャのワールド空間トライプラナー投影（Triplanar）。 | `texture`, `position`, `normal` (+15 optional) |
| `cop_triplanar_uv` | COPフィルター：ワールド位置＋法線パスからトライプラナーUV座標を生成（Triplanar UV）。 | `position`, `normal` (+2 optional) |
| `cop_triplanar_hextile` | COPフィルター：セルごとの六角タイルのランダム化を伴うトライプラナー投影（Triplanar Hex Tile）。 | `input` (+11 optional) |
| `cop_uv_map` | COPジェネレーター：UVレイヤーを生成（UV Map）。uv_space（texture/image/pixel）、u_border/v_border（clamp/mirror/wrap/extend）、u_shift/u_cycle、v_shift/v_cycle。 | 8 optional |
| `cop_pos_map` | COPジェネレーター：ワールド位置レイヤーを生成（Position Map）。source（pos/origin/view）、軸ごとの x/y/z border（clamp/mirror/wrap/extend）、x/y/z の shift＋cycle、signature（mono/vec3/...）。 | 12 optional |
| `cop_corner_pin` | COPフィルター：透視のコーナーピンワープ（Corner Pin）。 | `input` (+6 optional) |
| `cop_lens_distort` | COPフィルター：放射＋接線のレンズ歪み／歪み補正（Lens Distort）。k1..k6 = 放射係数、p1/p2 = 接線、center [x,y]、scale [x,y]、aspect、mask。 | `input` (+13 optional) |
| `cop_uv_to_polar` | COPフィルター：UVレイヤーを極（角度、長さ）座標へ変換（UV to Polar) -- cop_polar_to_uv の逆。angle_unit（rad/deg/tau）。 | `input` (+2 optional) |
| `cop_fractal_noise_3d` | COPジェネレーター：ワールド空間（3Dサンプリング）のフラクタルノイズ（Fractal Noise 3D）。noise_type（simplex/perlin/worleyA/worleyB/white/alligator）、metric、amp/center/contrast、element_size、octaves、lacunarity、roughness、jitter、offset [x,y,z]、post の bias/gain（自動有効化）、complement。 | 16 optional |
| `cop_worley_noise_3d` | COPジェネレーター：ワールド空間のセルラー／Worleyノイズ（Worley Noise 3D）。element_size/element_scale、jitter/jitter_scale、metric、offset [x,y,z]、post の bias/gain（自動有効化）、complement。 | 11 optional |
| `cop_crystal_noise_3d` | COPジェネレーター：ワールド空間のファセット状結晶質Worleyノイズ（Crystal Noise 3D）。metric、amp/center/contrast、jitter、element_size、secondary＋metric2、flatten_faces、offset [x,y,z]、signature。 | 12 optional |
| `cop_cloud_noise_3d` | COPジェネレーター：ワールド空間のもくもくとした雲ノイズ（Cloud Noise 3D）。amp/center、element_size、offset [x,y,z]、max_octaves、lacunarity、roughness、distort、stretch [x,y,z]、droop（自動有効化）、fold、signature、post の bias（自動有効化）。 | 14 optional |
| `cop_xform_2d` | COPフィルター：2D画像変換（Transform 2D）。translate [x,y]、rotate、scale_xy [x,y]＋uniform scale、shear、pivot [x,y]、xform_order、border、filter、invert。 | `input` (+11 optional) |
| `cop_vector_xform` | COPフィルター：レイヤー内の3ベクトルの値を変換（Vector Transform) -- 法線／位置／速度レイヤー用。translate/rotate/scale_xyz/shear/pivot（各 [x,y,z]）、uniform scale、xform_order、rot_order、invert。 | `input` (+10 optional) |
| `cop_vector_xform_2d` | COPフィルター：レイヤー内の2ベクトルの値を変換（Vector Transform 2D) -- UV／フローレイヤー用。translate [x,y]、rotate、scale_xy [x,y]＋uniform scale、shear、pivot [x,y]、xform_order、invert。 | `input` (+9 optional) |
| `cop_space_transform` | COPフィルター：レイヤー値を座標空間間で変換（Space Transform）。vector_type（position/vector）、src_space＋dst_space（buffer/pixel/texture/image/world）。 | `input` (+4 optional) |
| `cop_bend` | COPフィルター：レイヤーをベンド／ワープ（Bend）。 | `input` (+15 optional) |
| `cop_id_to_mask` | COPフィルター：選択したIDから0/1のマスクを構築（ID to Mask）。 | `input` (+10 optional) |
| `cop_mono_to_sdf` | COPフィルター：iso 閾値を基準にモノレイヤーを符号付き距離場へ変換（Mono to SDF）。invert、iso、iterations、tile_size。 | `input` (+5 optional) |
| `cop_denoise_tvd` | COPフィルター：全変動拡散のデノイズ（Denoise TVD) -- 純粋な数学処理であり、AIモデルではありません。iterations、speed、mask。 | `input` (+4 optional) |
| `cop_fill_connected` | COPフィルター：許容差の範囲内でシードから連結領域をフラッドフィル（Fill Connected）。seed_location [x,y]、source_location [x,y]、tolerance、source（value/sample/first/last）、color [r,g,b,a]、id。 | `input` (+7 optional) |
| `cop_ill_pixel` | COPフィルター：不正ピクセルを検出／修正／フラグ付け（Illegal Pixel）。method（fixblend/fixzero/highlight/isolate）、detect（d_nan/d_inf/both/custom）、rule（less/lessequal/greater/greaterequal/equal）、compare_value、highlight_color [r,g,b,a]。 | `input` (+6 optional) |
| `cop_bound_rect` | COPフィルター：閾値を通過するピクセルを囲むバウンディング矩形のマスク（Bound Rect）。side（less/greater）、threshold、fg/bg、units（image/texture/pixel）。 | `input` (+6 optional) |
| `cop_hyperbolic_tile` | COPジェネレーター：双曲（ポアンカレ円板）の正多角形タイリング（Hyperbolic Tiling）。iterations、polygon（辺の数）、mapping（conformal/elliptic grid/squircle/equalarea）、flattening、size、tile_fitting、rectanglize/stretch_to_fit/disk_mask。 | 10 optional |
| `cop_convert_depth` | COPフィルター：レイヤーを深度／距離／高さのエンコーディング間で変換（Convert Depth）。source＋dest（depth/dist/height）、zero_depth。 | `input` (+4 optional) |
| `cop_zcomp` | COPコンポジター：2つのレイヤーをZ深度でコンポジットし、最も近い面を優先（Z Composite）。 | `input`, `fg` (+5 optional) |
| `cop_uv_map_by_id` | COPフィルター：IDレイヤーからアイランドごとのUVマップ（または center/min/max/size）を生成（UV Map by ID）。 | `input` (+11 optional) |
| `cop_project_on_layer` | COPフィルター：ソースレイヤーをターゲットレイヤーの空間へ再投影（Project on Layer）。 | `input`, `source` (+4 optional) |
| `cop_contact_sheet` | COPコンバイナー：複数の入力レイヤーをモンタージュ／コンタクトシートにタイル配置（Contact Sheet）。 | `inputs` (+8 optional) |
| `cop_copy_xform` | COPフィルター：シェイプの変換済みコピーをN個スタンプ（Copy Transform）。 | `input` (+14 optional) |
| `cop_lattice_deform` | COPフィルター：4x4のラティスグリッドを通してレイヤーをワープ（Lattice Deform）。 | `input` (+6 optional) |
| `cop_surface_dither` | COPフィルター：サーフェス安定なハーフトーン／ディザパターン -> マスクまたはSDF（Surface Dither）。 | `input` (+10 optional) |
| `cop_sample` | COPフィルター：UVマップを通してテクスチャをリサンプル（Sample）。 | `input`, `texture` (+4 optional) |
| `cop_prefix_sum` | COPフィルター：画像を横断する方向性の累積スキャン（Prefix Sum）。sweep_dir（px/mx/py/ny/xy/index）、op（add/min/max/count）、scale（none/pixel/texture/image）。 | `input` (+4 optional) |
| `cop_statistics` | COPフィルター：レイヤーごとの統計（min/max/avg/...）をレイヤーアトリビュートとして算出（Statistics）。下流ノードから読み取り可能。 | `input` (+1 optional) |
| `cop_layer_properties` | COPフィルター：レイヤーの精度／境界／タイプ情報のメタデータを設定（Layer Properties）。precision（b8/b16/b32）、border（constant/clamp/mirror/wrap）、type_info（color/position/normal/id/mask/sdf/height/...） -- それぞれが対応するセッターを自動有効化。 | `input` (+4 optional) |
| `cop_rgb_to_rgba` | COPフィルター：RGBレイヤーをアルファレイヤーと結合 -> RGBA（RGB to RGBA）。 | `input` (+3 optional) |
| `cop_rgba_to_rgb` | COPフィルター：アルファチャンネルを破棄 -> RGB（RGBA to RGB）。unpremult（先に乗算解除）。 | `input` (+2 optional) |
| `cop_id_to_mono` | COPフィルター：IDレイヤーをモノのfloatレイヤーへ変換（ID to Mono）。conversion（cast/safe/bitwise）。 | `input` (+2 optional) |
| `cop_mono_to_id` | COPフィルター：モノレイヤーをIDレイヤーへ変換（Mono to ID）。conversion（cast/safe/bitwise）。 | `input` (+2 optional) |
| `cop_id_to_rgb` | COPフィルター：IDごとにランダムなカラーを割り当て（ID to RGB）。seed。 | `input` (+2 optional) |
| `cop_rgb_to_uv` | COPフィルター：RGBレイヤーをUV（2ベクトル）レイヤーとして再解釈（RGB to UV）。 | `input` (+1 optional) |
| `cop_uv_to_rgb` | COPフィルター：UVレイヤーをRGBとして再解釈（UV to RGB）。オプションの `mono` レイヤー -> input 1 が青チャンネルを供給。 | `input` (+2 optional) |
| `cop_rgba_to_uv` | COPフィルター：RGBAレイヤーをUV（2ベクトル）レイヤーとして再解釈（RGBA to UV）。 | `input` (+1 optional) |
| `cop_uv_to_rgba` | COPフィルター：2つの2ベクトルレイヤーをRGBAに結合（UV to RGBA）。 | `input` (+2 optional) |
| `cop_channel_split` | COPフィルター：マルチチャンネルレイヤーを単一チャンネルの出力へ分割（Channel Split) -- cop_channel_join の逆。 | `input` (+1 optional) |
| `cop_layer_attrib_create` | COPフィルター：レイヤーメタデータのアトリビュートを追加（Layer Attribute Create）。attr_name、attr_type（string/float/int）、value（型に応じた値）。 | `input` (+4 optional) |
| `cop_layer_attrib_delete` | COPフィルター：名前のグロブでレイヤーメタデータのアトリビュートを削除（Layer Attribute Delete）。delete（削除するグロブ）、keep（保持するグロブ）。 | `input` (+3 optional) |
| `cop_dot` | COPフィルター：2つのベクトルレイヤーのピクセルごとの内積 -> モノ（Dot）。 | `input`, `b` (+1 optional) |
| `cop_cross` | COPフィルター：2つのvec3レイヤーのピクセルごとの外積（Cross）。 | `input`, `b` (+1 optional) |
| `cop_pos_sample` | COPフィルター：位置レイヤーから読み取った座標でテクスチャをサンプリング（Position Sample）。 | `input`, `texture` (+1 optional) |
| `cop_statistics_by_id` | COPフィルター：IDごとの統計をレイヤーアトリビュートとして算出（Statistics by ID）。 | `input`, `source` (+1 optional) |
| `cop_match_udim` | COPフィルター：画像を指定したUDIMタイルへ再配置（Match UDIM）。udim（タイル番号、set_udim を有効化）、invert、method（eye/data）。 | `input` (+4 optional) |
| `cop_autostereogram` | COPフィルター：パターン＋深度画像からマジックアイのオートステレオグラムを構築（Autostereogram）。 | `input`, `depth` (+5 optional) |
| `cop_uv_xform` | COPフィルター：UVレイヤーを平行移動／回転／スケール（UV Transform）。translate [x,y]、rotate、scale_xy [x,y]＋uniform scale、pivot [x,y]、seed。 | `input` (+7 optional) |
| `cop_layer` | COPジェネレーター：指定した解像度／精度の空の型付きレイヤー（Layer）。signature（f1/f2/f3/f4/i）、value（モノの初期化）、res [w,h]、precision（b8/b16/b32）、border（constant/clamp/mirror/wrap）、type_info。 | 7 optional |
| `cop_heat_distort` | COPフィルター：内部ノイズによる陽炎の歪み（Heat Distort）。global_scale、scale、element_size、detail_scale、roughness、cutoff、angle、distort/detail_distort/streak_blur のトグル、mask。 | `input` (+12 optional) |
| `cop_heat_distort_by_layer` | COPフィルター：`noise` レイヤーで駆動される陽炎の歪み（Heat Distort by Layer）。 | `input`, `noise` (+9 optional) |
| `cop_heightfield_visualize` | COPフィルター：入力のハイトフィールドレイヤーを可視化用にスケール／オフセット（Heightfield Visualize）。height_scale、height_offset。 | `input` (+3 optional) |
| `cop_sop_import` | COPジェネレーター：シーン内のSOPをcopnetへブリッジ（SOP Import）。 | `sop` (+1 optional) |
| `cop_rasterize_geo` | COP：ジオメトリアトリビュートを画像レイヤーへラスタライズ（Rasterize Geometry）。 | `geometry` (+6 optional) |
| `cop_rasterize_setup` | COP：Rasterize Geometry に先行するラスタライズ用カメラ／空間を構成（Rasterize Setup）。 | `geometry` (+7 optional) |
| `cop_rasterize_curves` | COP：カーブジオメトリをストロークとしてレイヤーへラスタライズ（Rasterize Curves）。 | `curves` (+10 optional) |
| `cop_layer_to_geo` | COP：COPレイヤーをSOPジオメトリへ戻す（Layer to Geometry) -- ボリューム／VDBプリミティブ。 | `input` (+3 optional) |
| `cop_layer_to_points` | COP：COPレイヤーからSOPポイントを生成（Layer to Points）。 | `input` (+6 optional) |
| `cop_layer_from_curves` | COP：カーブジオメトリから着色／プロファイル付きのストロークをレイヤーへ（Layer from Curves）。 | `curves` (+7 optional) |
| `cop_mask_from_curves` | COP：カーブジオメトリからマスクまたはSDFを生成（Mask from Curves）。 | `curves` (+7 optional) |
| `cop_geo_to_layer` | COP：ジオメトリから名前付きのプリミティブ／VDBを型付きレイヤーへ読み込み（Geometry to Layer）。 | `geometry` (+3 optional) |
| `cop_vdb_posmap` | COP：VDBのボクセル位置マップ（VDB Pos Map）。 | `input` (+3 optional) |
| `cop_layer_from_vdb` | COP：FloatVDBレイヤーをサンプリングされたCOPレイヤーへ変換（Layer from VDB）。 | `input` (+2 optional) |
| `cop_vdb_from_layer` | COP：COPレイヤーを、参照VDBに合わせてサイズ調整したVDBへ変換（VDB from Layer）。 | `input`, `reference_vdb` (+2 optional) |
| `cop_rasterize_volume` | COP：密度VDBレイヤーをレイマーチして画像へ（Rasterize Volume）。 | `input` (+8 optional) |
| `cop_integrate_volume` | COP：ボリュームレイヤーをレイ積分してモノへ（Integrate Volume) -- 深度／厚み。 | `input` (+6 optional) |
| `cop_pyro_configure` | COP pyro：シムのボクセルグリッドを定義（Pyro Configure）。 | 8 optional |
| `cop_pyro_source_from_layer` | COP pyro：ソースレイヤーからフィールドへ放出（Pyro Source from Layer）。 | `input`, `density` (+12 optional) |
| `cop_pyro_source_from_points` | COP pyro：ポイントソースからフィールドへ放出（Pyro Source from Points）。 | `input`, `points` (+8 optional) |
| `cop_pyro_advect` | COP pyro：速度VectorVDBでフィールドを移流（Pyro Advect）。 | `input`, `velocity` (+12 optional) |
| `cop_pyro_buoyancy` | COP pyro：温度駆動の浮力を速度に加える（Pyro Buoyancy）。 | `input`, `temperature` (+13 optional) |
| `cop_pyro_dissipate` | COP pyro：フィールドを時間とともに散逸させる（Pyro Dissipate）。 | `input` (+17 optional) |
| `cop_pyro_disturbance` | COP pyro：速度にディスターバンスのディテールを加える（Pyro Disturbance）。 | `input` (+12 optional) |
| `cop_pyro_turbulence` | COP pyro：速度に乱流／カールノイズのディテールを加える（Pyro Turbulence）。 | `input` (+15 optional) |
| `cop_pyro_uniform_force` | COP pyro：速度に均一な方向性フォース／ドラッグを適用（Pyro Uniform Force）。 | `input` (+13 optional) |
| `cop_pyro_activate` | COP pyro：シムのアクティブなボクセル領域を成長／アクティブ化（Pyro Activate）。 | `input` (+12 optional) |
| `cop_pyro_advect_by_map` | COP pyro：事前計算した順／逆の移流マップでフィールドを移流（Pyro Advect by Map）。 | `input`, `fwd_map` (+5 optional) |
| `cop_pyro_build_advection_map` | COP pyro：速度フィールドから順／逆の移流マップを構築（Pyro Build Advection Map）。 | `input` (+7 optional) |
| `cop_pyro_axis_force` | COP pyro：軸まわりの渦／軸／オービットのフォース（Pyro Axis Force）。 | `input` (+17 optional) |
| `cop_pyro_light_ambient` | COP pyro：密度フィールドへのアンビエント／環境光の寄与（Pyro Light Ambient）。 | `input` (+14 optional) |
| `cop_pyro_light_from_points` | COP pyro：密度フィールドへのポイント／指向性ライトの散乱（Pyro Light from Points）。 | `input` (+14 optional) |
| `cop_pyro_light_scatter` | COP pyro：密度＋発光を通した多重散乱ライト（Pyro Light Scatter）。 | `input` (+8 optional) |
| `cop_pyro_project_electrostatic` | COP pyro：静電投影により速度フィールドを非発散化（Pyro Project Non Divergent Electrostatic）。 | `input`, `reference` (+12 optional) |
| `cop_pyro_packed_mipmap` | COP pyro：パック済みの密度ミップマップを構築（Pyro Packed Mipmap) -- ライトのマイクロソルバー（cop_pyro_light_ambient ／ cop_pyro_light_from_points）の `mipmap` 入力へ供給するアクセラレーター。 | `input` (+3 optional) |
| `cop_pyro_block_begin` | COP pyro：pyroフィードバックブロックループの開始（Pyro Block Begin) -- 反復ごとのフィールド状態をシードします。 | `input`, `velocity`, `temperature` (+11 optional) |
| `cop_pyro_block_end` | COP pyro：pyroフィードバックブロックループの終了（Pyro Block End) -- ループを閉じ、ループ制御を保持します。 | `input`, `velocity`, `temperature`, `block_begin` (+14 optional) |
| `cop_pyro_solver` | COP pyro のマクロ（1回の呼び出し）：最小限のCOPネイティブなpyroフィードバックソルブのループをスタンプ -- cop_pyro_block_begin（ループ開始、反復ごとの density/v/temperature をシード） -> 最小限のpyro移流のボディ（ループ密度をループ速度で移流） -> cop_pyro_block_end（ループを閉じ、ループ制御を保持）を自動配線し、begin<->end のブロックパス連携を設定します。 | `input`, `velocity`, `temperature` (+6 optional) |
| `cop_vdb_leafpoints` | COP：VDBのリーフ／ボクセル中心にポイントを生成（VDB Leaf Points）。 | `input` (+2 optional) |
| `cop_layer_to_vdb_leafpoints` | COP：レイヤーからVDBリーフのサンプルポイントを生成（Layer to VDB Leaf Points）。 | `input`, `thickness_layer` (+3 optional) |
| `cop_vdb_activate_from_points` | COP：ポイント位置からVDBのボクセル領域をアクティブ化（VDB Activate from Points）。 | `input`, `points` (+5 optional) |
| `cop_vdb_reshape` | COP：VDBを参照VDBの変換／トポロジーのフレームに適合させる（VDB Reshape）。 | `input`, `reference` (+1 optional) |
| `cop_stamp_point` | COP：ポイント位置にレイヤーをスタンプ（Stamp Point）。 | `points`, `stamps` (+17 optional) |
| `cop_curve_scatter` | COP：カーブに沿ってスタンプをスキャッター（Curve Scatter）。 | `curves`, `stamps` (+18 optional) |
| `cop_shape_scatter` | COP：画像グリッド全体にスタンプをスキャッター（Shape Scatter) -- ジオメトリ不要。 | `stamps` (+18 optional) |
| `cop_rasterize_layer` | COP：既存のレイヤーを再ラスタライズ／再投影（Rasterize Layer）。 | `input` (+5 optional) |
| `cop_vdb_visualize` | COP：密度VDBを画像へシェーディング（VDB Visualize）。 | `input` (+10 optional) |
| `cop_vdb_visualize_slice` | COP：スライス平面によるVDBの可視化（VDB Visualize Slice）。 | `input` (+9 optional) |
| `cop_vdb_visualize_tree` | COP：VDBのツリー／トポロジーの可視化（VDB Visualize Tree）。 | `input` (+8 optional) |
| `cop_vdb_visualize_velocity` | COP：VDBの速度フィールドの可視化（VDB Visualize Velocity）。 | `input` (+9 optional) |
| `cop_raytrace` | COP：ジオメトリをレイトレースしてAO／曲率／厚み／キャビティ／エッジのマップを生成（Raytrace）。 | `geometry`, `origins`, `directions` (+16 optional) |
| `cop_bake_geometry_textures` | COP：ジオメトリから法線／AO／曲率／位置／厚み／高さのマップをベイク（Bake Geometry Textures）。 | `low` (+17 optional) |
| `cop_file` | COPジェネレーター：ディスクから画像を読み込み（File）。 | `filename` (+1 optional) |
| `cop_rop_image` | COP出力ドライバー：入力のCOPストリームをディスク上の画像へ書き出し（ROP Image Output）。 | `input`, `output` (+3 optional) |
| `cop_font` | COP：テキストを画像としてレンダリング（Font）。 | 4 optional |
| `cop_onnx` | COP：画像に対してONNXモデルの推論を実行（ONNX Inference）。 | `input` (+2 optional) |
| `cop_slapcomp_import` | COP：インメモリのスラップコンプ・レンダーバッファを取り込み（Slap Comp Import）。 | 4 optional |
| `cop_cache` | COP：入力レイヤーのフレームごとのインメモリキャッシュ（Cache）。 | `input` (+3 optional) |
| `cop_fetch` | COPジェネレーター：別のCOPノードの出力をパスで取得（Fetch）。 | 2 optional |
| `cop_camera_import` | COPジェネレーター：シーンカメラのパラメーターをインポート（Camera Import）。 | 2 optional |
| `cop_ocio_transform` | COP：OpenColorIOのカラースペース変換を適用（OCIO Transform）。 | `input` (+5 optional) |
| `cop_live_video` | COPジェネレーター：ライブビデオ／ウェブカメラデバイスからフレームをキャプチャ（Live Video）。 | 3 optional |
| `cop_denoise_ai` | COP：入力レイヤーをAIデノイズ（Denoise AI）。 | `input` (+2 optional) |
| `cop_cryptomatte` | COPフィルター：cryptomatteレイヤーから単一のカバレッジマットを抽出（Cryptomatte）。 | `input` (+3 optional) |
| `cop_cryptomatte_decode` | COPフィルター：パック済みcryptomatteレイヤーをid／coverageのランクペアへデコード（Cryptomatte Decode）。 | `input` (+1 optional) |
| `cop_cryptomatte_encode` | COPフィルター：id／coverageのランクペアを1つのパック済みcryptomatteレイヤーへエンコード（Cryptomatte Encode）。 | `input`, `cov_a`, `id_b`, `cov_b` (+1 optional) |
| `cop_grunge_aurora` | COPジェネレーター：オーロラ／筋状ベールの風化パターン（Grunge Aurora）。 | 21 optional |
| `cop_grunge_birchbark` | COPジェネレーター：白樺の樹皮のマテリアルパターン（Grunge Birch Bark）。 | 24 optional |
| `cop_grunge_layered_noise` | COPジェネレーター：4層コンポジットのノイズ（Grunge Layered Noise) -- ベースノイズ＋ベースセル＋二次ノイズ＋二次セル。 | 29 optional |
| `cop_grunge_pinebark` | COPジェネレーター：松の樹皮のマテリアルパターン（Grunge Pine Bark）。 | 21 optional |
| `cop_grunge_rust` | COPジェネレーター：錆／腐食のパターン（Grunge Rust）。 | 22 optional |
| `cop_cable_merge` | COP：2つのCopernicusケーブルを結合（Cable Merge) -- `input` = input_cable（input 0）、`reference` = 2つ目のケーブル（input 1）。operation（union/intersection/difference/copy/fullunion/rename）が2つのワイヤーセットの結合方法を制御します。 | `input` (+3 optional) |
| `cop_cable_split` | COP：Copernicusケーブルのワイヤーを2つのケーブルへ分割（Cable Split）。 | `input` (+16 optional) |
| `cop_cable_pack` | COP：名前付きのワイヤーを1つのCopernicusケーブルへ組み立て（Cable Pack）。 | `input` (+2 optional) |
| `cop_cable_unpack` | COP：Copernicusケーブルから名前付きのワイヤーを取り出し（Cable Unpack）。 | `input` (+2 optional) |
| `cop_cable_filter` | COP：Copernicusケーブルから空のワイヤーを除去（Cable Filter）。 | `input` (+1 optional) |
| `cop_cable_sort` | COP：ケーブルのワイヤーを名前でアルファベット順にソート（Cable Sort）。 | `input` (+2 optional) |
| `cop_cable_switch` | COP：2つのケーブルのうち1つを選択（Cable Switch）。 | `input` (+3 optional) |
| `cop_cable_rename` | COP：パターン置換でケーブルのワイヤーをリネーム（Cable Rename）。 | `input` (+5 optional) |

### 画像 / テクスチャ

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `sbs_archive` | SideFX Labs SBS Archive — Substance の `.sbsar` アーカイブを読み込み、そのレンダリング済みテクスチャを共有の /obj/cops2 cop2net へ出力するCop2ジェネレーター。 | 3 optional |
| `blackbody_texture` | SideFX Labs Blackbody（labs::blackbody_cop） — 温度（ケルビン）を、temperature_low から temperature_high にかけて画像全体で放出される黒体色へマッピングするCop2ジェネレーター。tonemap／gamma／adaptation／burn の制御付き。 | 12 optional |
| `attribute_to_texture` | SideFX Labs Attribute Import（labs::attribute_import） — ジオメトリのポイント／頂点のアトリビュートを、そのジオメトリのUVレイアウト上でテクスチャへラスタライズするCop2ジェネレーター。 | 6 optional |
| `grid_texture` | SideFX Labs Grid Texture（labs::grid_texture） — UVのチェッカー／グリッド参照テクスチャを生成するCop2ジェネレーター。オプションでタイルごとのテキスト、境界、色を付与。 | 12 optional |
| `normal_color` | SideFX Labs Normal Color（labs::normal_color） — 指定した解像度で、フラットなタンジェント空間の法線マップ色フィールド（デフォルトの「上」向き法線、RGB 0.5/0.5/1）を出力するCop2ジェネレーター。ディテール法線を合成するためのベースレイヤー。 | 2 optional |
| `normal_map` | SideFX Labs Normal Map（labs::normal_map） — 入力の高さ／グレースケール画像（input 0）をタンジェント空間の法線マップへ変換するCop2フィルター。 | `input` (+5 optional) |
| `normal_combine` | SideFX Labs Normal Combine（labs::normal_combine） — ディテール法線マップ（input 1）をベース法線マップ（input 0）の上に、正しく再配向した法線ブレンドでレイヤーするCop2フィルター。 | `input`, `input2` (+1 optional) |
| `normal_invert` | SideFX Labs Normal Invert（labs::normal_invert） — タンジェント空間法線マップ（input 0）の選択した軸を反転するCop2フィルター。 | `input` (+4 optional) |
| `normal_levels` | SideFX Labs Normal Levels（labs::normal_levels） — 法線マップ（input 0）にレベル／ガンマのリマップを適用するCop2フィルター。 | `input` (+4 optional) |
| `normal_rotate` | SideFX Labs Normal Rotate（labs::normal_rotate） — 入力法線マップ（input 0）のタンジェント空間法線ベクトルを、サーフェス法線まわりに `angle` 度だけ回転するCop2フィルター（UV上でテクスチャを回転させたときにマップの整合性を保ちます）。 | `input` (+2 optional) |
| `normal_normalize` | SideFX Labs Normal Normalize（labs::normal_normalize） — 入力法線マップ（input 0）の全ピクセルを単位長へ再正規化するCop2フィルター（ブレンドやフィルタリング後の非単位法線を修正）。 | `input` (+1 optional) |
| `vector_normalize` | SideFX Labs Vector Normalize（labs::vector_normalize） — 入力ベクトル画像（input 0）を正規化された範囲へ再スケールするCop2フィルター。`enable` で有効化し、`min`／`max` がベクトルの大きさを収める目標範囲を設定します。 | `input` (+4 optional) |
| `demosaic` | SideFX Labs Demosaic（labs::demosaic） — rows x columns のスプライトアトラス／フリップブックシート（input 0）を個々のフレームへ展開するCop2フィルター。`frame` がタイルを選択し、`start_frame` が番号付けをオフセットします。 | `input` (+5 optional) |
### Solaris / LOP / USD

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `usd_layer` | 複数ブランチのUSD / Solarisステージのアセンブリ＆レイヤーコンポジション（LOP）。op=mergeは複数のLOPブランチを1つのステージに統合します（`inputs`をinput0..Nに配線。mergestyleはレイヤーコンポジション/フラット化スタイルを設定し、デフォルトはflattenloplayers = Simple Merge）。op=sublayerは外部の.usd/.usda/.usdcファイルをサブレイヤーとして合成します（`files`は読み取り制限。`input` = 重ねる対象のLOP）。op=graftはソースのサブツリーを配置先primの下に差し込みます（`input`=Input Stage、`source`=input1にグラフトするLOP、`primpath`=配置先の親prim、`src_prims`/`dst_prims`=ソースおよび配置先のprimパス）。 | 10 optional |
| `usd_configure` | USD prim / アセットのメタデータを記述（LOP configureprimitive）、またはバリアントを選択します — 純粋なメタデータのみで、シェーダー/VEXはありません。op=configureは`primpattern`に一致するprimに対して次を設定します：kind（assembly\|group\|component\|subcomponent、アセット階層）、purpose（default\|proxy\|render\|guide）、drawmode（default\|origin\|bounds\|cards — USDネイティブのプロキシLODで、重いアセットはアセンブリステージではbounds/cardsとして描画され、レンダー時にはフルジオメトリになります）、instanceable（bool）、visibility（inherit\|invisible\|visible — primの表示/非表示）、specifier（def\|over\|class）。op=variantはバリアントセット/名を選択します（LODまたはルックの切り替え）。 | 12 optional |
| `sop_import` | SOPネットワークのジオメトリをUSDステージに取り込みます — SOP->Solarisブリッジ。 | `soppath` (+6 optional) |
| `usd_import` | USDファイルをreference / payload / sublayerとしてステージに合成します。 | `path` (+4 optional) |
| `usd_light` | ステージにUSD/Karmaライトを追加/調整します（light::2.0またはdomelight::3.0）。 | 27 optional |
| `usd_camera` | USDステージにカメラprimを追加/調整します（camera LOP）。 | 20 optional |
| `karma_render_settings` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：LOPでKarmaレンダーグラフを構築します（render-settings prim + usdrender ROP）。 | 14 optional |
| `render_geo_settings` | USDステージ上でprimごとのKarmaレンダー設定を記述します（Render Geometry Settings LOP） — デリバリーレーンの主力ツール：プライマリレイの可視性（`visibility`をKarmaカテゴリーのglobに設定 — cameraを除外するとPHANTOM / 反射専用のprimになります）、holdout/MATTEモード、モーション + 速度ブラー、uniform-volumeの解釈、dicing品質。 | `input` (+9 optional) |
| `karma_fog_box` | USDステージに大気のFOGボリュームを追加します（Karma Fog Box LOP） — box/sphereなどのバウンド内で均一またはノイズ変調したフォグを生成し、地平線のかすみ / ゴッドレイ / 奥行き表現に使います。 | 17 optional |
| `physical_sky` | ステージに物理ベースのKarma空 + 太陽を構築します（karmaphysicalsky） — 地形/globeの太陽スタディ用プリミティブ。 | 20 optional |
| `light_link` | lightlinker LOPを介して、ライトが照らす/照らさないジオメトリを制限します — データ専用のprim-pattern文字列で、式はありません。 | `light`, `geo` (+4 optional) |
| `assign_usd_material` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：MaterialX Standard Surfaceマテリアルを記述し、USDステージ上のprim_patternにバインドします — テクスチャ付きKarmaフレームへの型付き経路（materiallibrary + mtlxstandard_surface + assignmaterial。VEXなし、コードなし）。 | `prim_pattern` (+24 optional) |
| `material_graph_create` | 空のプロシージャルなMaterialXマテリアルグラフを作成します — /stage LOPのmateriallibraryで、shader_node_add / shader_connect / shader_set_paramで内容を埋め、material_graph_assignでバインドします。 | 2 optional |
| `shader_node_add` | マテリアルグラフにMaterialXノードを1つ追加します（libraryはmaterial_graph_createから）。node_type = 許可リスト化されたmtlx*タイプ：mtlxstandard_surface（PBRシェーダーのターミナル）、mtlximage/mtlxtriplanarprojection（テクスチャ）、mtlxnoise3d/mtlxfractal3d/mtlxworleynoise3d（ノイズ）、mtlxramplr/mtlxramp4（ランプ）、mtlxgeompropvalue（ジオメトリアトリビュート/地形レイヤーの読み取り）、mtlxmix/mtlxremap/mtlxmultiply/mtlxclamp（数学）、mtlxnormalmap/mtlxdisplacement（法線/ディスプレイスメント）。signatureはノードのデータ型を設定します。 | `library`, `node_type` (+2 optional) |
| `shader_connect` | あるMaterialXノードの出力を別のノードの入力に配線します（グラフのエッジを構築）。dst_inputは入力の名前（例：base_color、specular_roughness、normal、texcoord、in1）または数値インデックス。src_outputはデフォルトで'out'（すべてのmtlxノードが持つ単一の出力）。 | `dst`, `dst_input`, `src` (+1 optional) |
| `shader_set_param` | MaterialXノードに型付きのリテラルを設定します — signature-suffixの罠を自動的に処理します。param = ベースのparm名（例：amplitude、valuel、valuer、geomprop、file、octaves、inlow、outhigh）。value = 数値、[r,g,b]/[x,y,z]リスト、または文字列。 | `node`, `param`, `value` |
| `material_graph_assign` | 構築したマテリアルグラフをUSDステージ上のジオメトリにバインドします（materiallibrary + assignmaterial）。shader = ターミナルノード（mtlxstandard_surface、またはsurface+displacementを結合するcollect/mtlxsurfacematerial）。prim_pattern = バインドするジオメトリのprimパス/パターン（必須。ワイルドカードにはis_patternを設定）。 | `library`, `shader`, `prim_pattern` (+2 optional) |
| `material_ramp_on_attribute` | 主力の1コールレシピ：ジオメトリアトリビュート上のランプからカラーシェーダーチャンネルを駆動します — 地形の height->color イディオム。 | 10 optional |
| `material_noise_channel` | 1コールレシピ：プロシージャルノイズからスカラーシェーダーチャンネルを駆動します。 | 12 optional |
| `usd_prim_cube` | ステージにUSD Cube primを作成します（cube LOP）：size + transform。 | 12 optional |
| `usd_prim_cone` | ステージにUSD Cone primを作成します（cone LOP）：axis、height、radius、transform。 | 12 optional |
| `usd_prim_cylinder` | ステージにUSD Cylinder primを作成します（cylinder::2.0 LOP）：axis、height、radii。 | 12 optional |
| `usd_prim_sphere` | ステージにUSD Sphere primを作成します（sphere LOP）：radius + transform。 | 12 optional |
| `usd_prim_capsule` | ステージにUSD Capsule primを作成します（capsule::2.0 LOP）：axis、height、radii。 | 12 optional |
| `usd_prim_mesh` | 空のUSD Mesh prim + サブディビジョンメタデータを作成します（mesh LOP）。 | 12 optional |
| `usd_prim_points` | ステージにUSD Points primを作成します（points LOP）：transform。 | 12 optional |
| `usd_prim_basiscurves` | ステージにUSD BasisCurves primを作成します（basiscurves LOP）：type、basis、wrap。 | 12 optional |
| `usd_prim_hermitecurves` | ステージにUSD HermiteCurves primを作成します（hermitecurves LOP）：transform。 | 12 optional |
| `usd_prim_primitive` | 任意のスキーマ型の汎用USD primを1つ作成します（primitive LOP）。 | 7 optional |
| `usd_instancer` | ステージにUSD PointInstancer / referenceベースのインスタンスを構築します（instancer LOP）。 | 17 optional |
| `usd_component_geometry` | 内部のSOPサブネットで駆動されるcomponentgeometryコンテナを作成します（fileパラメーターなし）。 | 10 optional |
| `usd_component_geometry_variants` | 複数の入力ステージをコンポーネント上のバリアントセットにパックします（componentgeometryvariants LOP）。 | 8 optional |
| `usd_component_material` | コンポーネントにマテリアルをバインドし、オプションでマテリアルバリアントセットを構築します（componentmaterial LOP）。 | `input` (+8 optional) |
| `usd_layout` | prototype primのインスタンスをステージ上に散布/配置します（layout LOP）。 | 14 optional |
| `usd_scene_import` | /objシーンオブジェクト（geo/lights/cameras）をステージに取り込みます（sceneimport::2.0 LOP）。 | 11 optional |
| `usd_graft_stages` | 別のステージのサブツリーを配置先primの下にグラフトします（graftstages LOP）。 | 9 optional |
| `usd_graft_branches` | ソースステージのブランチを配置先primにグラフトし、position/materialを保持します（graftbranches LOP）。 | 12 optional |
| `usd_restructure_scenegraph` | primの再ペアレント/リネームを行い、コンポジションアークを除去します（restructurescenegraph LOP）。 | `input` (+13 optional) |
| `usd_split_scene` | ステージを選択したブランチと残りの部分に分割します（splitscene LOP）。 | `input` (+4 optional) |
| `usd_isolate_scene` | 反復を高速化するためにステージの一部を分離します（isolatescene LOP）。 | `input` (+7 optional) |
| `usd_scope` | Scope（グループ化）primを作成し、オプションで一致したprimをその下に再ペアレントします（scope LOP）。 | 10 optional |
| `usd_collection` | ステージにUSDコレクション（名前付きのprim集合）を記述します（collection::2.0 LOP。iconパラメーターは除外）。 | 11 optional |
| `usd_prune` | ステージ上のprimを非アクティブ化または非表示にします（prune LOP）。 | 7 optional |
| `usd_split_primitive` | コンポーズされたprimを個別に編集可能なprimに分割します（splitprimitive LOP）。 | `input` (+8 optional) |
| `usd_xform` | 一致したprimにトランスフォーム（xformOp）を記述します（xform LOP）。 | `input` (+14 optional) |
| `usd_create_xform` | トランスフォームを持つ新しいXform primを作成します（createxform LOP）。 | 14 optional |
| `usd_point_xform` | SOPからのポイントアトリビュートでprimをトランスフォームします（pointxform LOP）。 | `input` (+5 optional) |
| `usd_transform_uv` | 一致したprimのUV/テクスチャ座標をトランスフォームします（transformuv LOP。map fileパラメーターは除外）。 | `input` (+13 optional) |
| `usd_resample_transforms` | アニメーションしたトランスフォームのタイムサンプルを固定間隔で再サンプリングします（resampletransforms LOP）。 | `input` (+4 optional) |
| `usd_duplicate` | 一致したprimをN回複製し、コピーごとに累積的なトランスフォームを適用します（duplicate LOP）。 | `input` (+15 optional) |
| `usd_retime_instances` | PointInstancerのインスタンスごとのタイムオフセット / リタイミング（retimeinstances LOP）。 | `input` (+11 optional) |
| `usd_extract_instances` | PointInstancerのインスタンスを実際のprimに抽出します（extractinstances LOP）。 | `input` (+12 optional) |
| `usd_merge_point_instancers` | 複数のPointInstancerを1つに統合します（mergepointinstancers LOP）。 | `input` (+3 optional) |
| `usd_split_point_instancers` | PointInstancerをprototype/アトリビュートごとにサブセットへ分割します（splitpointinstancers LOP）。 | `input` (+7 optional) |
| `usd_modify_point_instances` | PointInstancerの個々のインスタンスを編集します — インスタンスごとのトランスフォーム（modifypointinstances LOP）。 | `input` (+8 optional) |
| `usd_coordsys` | テクスチャ/投影空間用に名前付き座標系（coordsys）primをバインドします（coordsys LOP）。 | `input` (+13 optional) |
| `usd_edit_material` | USDマテリアルを編集用に開く / それをベースに新しいマテリアルを作成します（editmaterial LOP）。 | 6 optional |
| `usd_edit_material_properties` | マテリアルprimのプロパティを記述/編集します（editmaterialproperties LOP）。 | 12 optional |
| `usd_material_variation` | バインドされたマテリアルのシェーダーパラメーターをprim間で変化させます（materialvariation LOP）。 | `input` (+8 optional) |
| `usd_unassign_material` | 一致したprimからマテリアルバインディングを削除します（unassignmaterial LOP）。 | 7 optional |
| `usd_vary_material_assignment` | どのマテリアルをバインドするかをprim間でランダム/空間的に変化させます（varymaterialassignment LOP）。 | `input` (+16 optional) |
| `usd_light_distant` | ステージにUsdLux DistantLight（太陽）を作成します（distantlight::2.0 LOP）。 | 15 optional |
| `usd_light_portal` | ステージにUsdLux PortalLight（ドームライトのポータル）を作成します（portallight LOP）。 | 10 optional |
| `usd_light_geometry` | 一致したジオメトリをエミッシブなエリアライトに変換します（geometrylight LOP）。 | 15 optional |
| `usd_light_mixer` | ルック開発のために、ライトコレクションを介してライトをグループ化・トランスフォームします（lightmixer LOP）。 | 17 optional |
| `usd_shadow_catcher` | コンポジット用に、一致したprimをshadow-catcherサーフェスに変換します（shadowcatcher LOP）。 | 6 optional |
| `usd_light_filter_library` | light-filter primのライブラリを記述し、それらをライトに割り当てます（lightfilterlibrary LOP）。 | 10 optional |
| `usd_add_variant` | 入力ステージをprim上のバリアントセットにパックします（addvariant LOP）。 | 15 optional |
| `usd_explore_variants` | バリアントセットのすべてのバリアントを横並びにレイアウトします（explorevariants::2.0 LOP）。 | `input` (+16 optional) |
| `usd_create_lod` | primのポリゴン削減したLOD（level-of-detail）バリアントを構築します（createlod LOP）。 | `input` (+14 optional) |
| `usd_auto_select_lod` | カメラ距離に応じてLODバリアントを自動選択します（autoselectlod LOP）。 | `input` (+7 optional) |
| `usd_draw_mode` | 一致したprimにUSDイメージングの描画モード（bounds/cards/originプロキシ）を設定します（drawmode LOP）。 | 14 optional |
| `usd_configure_property` | 一致したUSDプロパティのメタデータを構成します（configureproperty LOP）。 | 9 optional |
| `usd_configure_stage` | ステージレベルのpopulation/load/muteルールを構成します（configurestage LOP）。 | 11 optional |
| `usd_edit_properties` | primとそのプロパティを一括で作成/編集します（editproperties LOP）。 | 12 optional |
| `usd_store_parameter_values` | 名前付きパラメーター値を再利用のためにステージデータとして保存します（storeparametervalues LOP）。 | 5 optional |
| `usd_set_extents` | 一致したprimのextent（bbox）ヒントを記述/再計算します（setextents LOP）。 | `input` (+8 optional) |
| `usd_edit_xform` | 一致したprimをトランスフォーム編集します（edit LOP）。 | 16 optional |
| `usd_layer_break` | レイヤーブレークを挿入し、下流の編集が新しいレイヤーに乗るようにします（layerbreak LOP）。 | 2 optional |
| `usd_set_variant` | 一致したprimでバリアントセットのどのバリアントをアクティブにするかを選択します（setvariant LOP）。 | `input` (+5 optional) |
| `usd_copy_property` | ソースprimから配置先primへプロパティ/アトリビュートをコピーします（copyproperty LOP）。 | `input` (+7 optional) |
| `usd_shot_split` | エディトリアルへの受け渡しのために、ステージ編集をショットごとのレイヤーに分割します（shotsplit LOP）。 | `input` (+8 optional) |
| `usd_shot_switch` | ショットアセンブリのために、候補となる入力ステージをインデックスで切り替えます（shotswitch LOP）。 | 4 optional |
| `shot_load` | ショットパイプラインからショットレイヤーを/stageに読み込みます（shotload LOP） — 構成済みのショットからステージを構築するエディトリアルの入口。 | 5 optional |
| `shot_output` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ショット用にステージをディスクに保存するShot Output ROP LOP（shotoutput）を構築します — 構成はされますが決して実行されません（書き込みはユーザーが実行）。outputは書き込み制限され、pre/post-renderのSCRIPTパラメーターは一切公開されません。 | `input`, `output` (+5 optional) |
| `shot_layer_edit` | ステージ編集を特定のショットレイヤーへ振り分けます（shotlayeredit LOP） — エディトリアルのレイヤーターゲッター。 | `input` (+6 optional) |
| `usd_value_clip` | クリップファイル群からアニメーションをストリーミングするUSD value-clip primを記述します（valueclip LOP）。clip_filesとmanifest_fileは作業ディレクトリにrealpathで制限されます。 | 9 optional |
| `usd_geometry_sequence` | アニメーションしたジオメトリファイルのシーケンスをステージに取り込みます（geometrysequence LOP） — フレームごとの.bgeo/.vdbキャッシュのストリーミング読み取りブリッジ。fileは読み取り制限されます（シーケンスには$Fトークンを使用）。 | `file` (+7 optional) |
| `usd_geo_clip_sequence` | USDジオメトリのvalue-clipシーケンスを読み込み / 書き込みます（geoclipsequence LOP） — アニメーションしたステージのサブツリーをフレームごとのクリップファイルにキャッシュし、それをストリーミングで読み戻します。load_clip_file（読み取り）とsave_clip_file（書き込み）はrealpathで制限されます。 | 13 optional |
| `usd_blend_constraint` | USD Blendコンストレイントを記述します — primのトランスフォームをsource + targetのprim間でブレンドします（blendconstraint LOP）。 | `input` (+9 optional) |
| `usd_followpath_constraint` | USD Follow-Pathコンストレイントを記述します — primをカーブに沿ってスライドさせます（followpathconstraint LOP）。 | `input` (+14 optional) |
| `usd_lookat_constraint` | USD Look-Atコンストレイントを記述します — primをターゲットに向けます（lookatconstraint LOP）。 | `input` (+11 optional) |
| `usd_parent_constraint` | USD Parentコンストレイントを記述します — primのトランスフォームをターゲットにペアレントします（parentconstraint LOP）。 | `input` (+14 optional) |
| `usd_points_constraint` | USD Pointsコンストレイントを記述します — primをターゲットの重み付きポイントに拘束します（pointsconstraint LOP）。 | `input` (+13 optional) |
| `usd_surface_constraint` | USD Surfaceコンストレイントを記述します — primをターゲットサーフェス上のUV位置にピン留めします（surfaceconstraint LOP）。 | `input` (+14 optional) |

### ルック、ライト＆カメラ

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `build_globe` | 解析的なlon/lat UVドレープ（「スキン」）を持つWGS84楕円体のglobeを構築し、equirectangularテクスチャとECEFにピン留めされたタイルが構造上一致するようにします。 | `name` (+12 optional) |
| `add_light` | hlight Typeパレット全体にドームを加えた範囲のライトを追加します。 | 21 optional |
| `add_camera` | リファレンス写真に一致させる / 画像を再現する / ショットをカメラソルブするためのカメラを作成します — レンダーがターゲット画像に揃うようにintrinsicsを設定します。焦点距離（mm）+ 絞り（mm）= 画角 / パースの圧縮（焦点距離が短いほど、または絞りが広いほど画角が広くなります）。resx/resy = 解像度ゲート。aspect。 | 17 optional |
| `camera_aim` | 既存のカメラをターゲットに向けます — データ専用（look-atの式/コンストレイントなし）。 | `camera` (+6 optional) |
| `camera_path` | OBJカメラをカーブSOPに沿ってアニメーションさせます — データ専用（計算されたリテラルのキーフレーム。Follow-Pathコンストレイント / $F式は使いません）。 | `curve` (+6 optional) |
| `setup_karma` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：OBJコンテキストのKarmaレンダーグラフ（camera + 解像度 + 出力画像に配線された/outの`karma` ROP）を構築し、未レンダーのまま返します — 実行は人間が行います（これによりリソースDoS / 重いシーンのフリーズという攻撃面が取り除かれます）。pictureは作業ディレクトリ配下に書き込まれます（拡張子でPNG/EXR/JPGを判定）。 | 9 optional |
| `setup_prorender` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：AMD Radeon ProRender（Hydraデリゲート`HdRprPlugin`）に設定したSolaris（/stage）USD-render ROPを構築し、未レンダーのまま返します — 実行は人間が行います（setup_karma / karma_render_settingsと同じ姿勢。リソースDoS / GPUクックのフリーズという攻撃面を取り除きます）。 | 5 optional |
| `substance_material` | SideFX Labs Substance Material — 入力ジオメトリ（input 0）にSubstanceマテリアルを割り当てます。 | `input` (+9 optional) |
| `quickmaterial` | SideFX Labs Quick Material — 入力ジオメトリ（`input`）に、オプションでプリミティブの`group`に対して、テクスチャマップ（`*_texture`、読み取り制限）とスカラーレバー（roughness / metallic / ior）で駆動しながら、マテリアルを1つ（Principled / MatCap / Labs PBR）割り当てます。 | `input` (+14 optional) |
| `set_view_camera` | Scene Viewerのビューポートを制御します：カメラを通して見る（ビューポートをそれにバインド）、および/または標準の正投影/透視ビュー（top/bottom/front/back/left/right/persp）に切り替え、オプションで全ジオメトリをビューに収まるようにフレーミングします。 | 4 optional |
| `flightcam` | poses .jsonで駆動されるキーフレーム付きのフライトカメラで、ソースクラウドをコンテキストとして読み込みます。 | `poses` (+7 optional) |
| `assign_material` | Material SOPを介して、入力SOPにPBRマテリアル / シェーダー（Principled Shader principledshader::2.0）を割り当て、サーフェスのルックでレンダーされるようにします — 型付きのリテラルパラメーター + テクスチャマップのみ（VOP/シェーダーグラフの記述はなし）。 | `input` (+26 optional) |
| `bake_texture` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：制限された出力でテクスチャベイクのグラフ（Bake Texture 3.0）を構築します。実行はしません。 | `output` (+3 optional) |
| `three_point_light` | Three Point LightリグOBJ（three_point_light）を作成します — key / fill / rim / bounceのライトを共有ターゲットに向けて1ノードにまとめます。 | 18 optional |
| `indirect_light` | Indirect（グローバルイルミネーションのバウンス）Light OBJ（indirectlight）を作成します。dimmerは間接光の寄与をスケールします。 | 6 optional |
| `ambient_light` | Ambient Light OBJ（ambient）を作成します — シーン全体に加えられる平坦で均一なフィル。 | 8 optional |
| `environment_fog` | Environment Fog OBJ（fog）を作成します — シーンを満たす大気ボリュームのコンテナ。t/r/s/scaleでフォグボックスのサイズと配置を決めます。 | 5 optional |
| `reference_image` | Reference Image OBJ（refimage）を作成します — モデリングのリファレンス / マッチング用の平面画像プレーン。image_fileは作業ディレクトリにrealpathで読み取り制限されます。 | 9 optional |
| `stereo_camera` | Stereo Camera OBJ（stereocam）を作成します — 左 + 右のカメラをグループ化するコンテナ。 | 7 optional |
| `stereo_camera_rig` | Stereo Camera Rig OBJ（stereocamrig）を作成します — interaxial / zero-parallaxのコントロールとカメラintrinsicsを備えた完全パラメトリックなステレオリグ。 | 14 optional |
| `vr_camera` | VR Camera OBJ（vrcam）を作成します — VRレンダー用のステレオパノラマカメラ（sphere/cylinder = equirectangular / 円筒パノラマ）。 | 14 optional |

### シーン、ナビゲーション＆ビューポート

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `scene_info` | 現在のHoudiniシーンを報告します：hipファイル、フレーム、バージョン、/objの内容。 | — |
| `read_network` | ネットワークの構造をテキストとして読み取ります — スクリーンショットに予算を費やすことなく、大きなノードグラフの全体像を（特にコンテキスト圧縮の後に）再構築するための、耐久性が高くトークン消費の少ないマップ。 | 5 optional |
| `set_frame` | 現在のタイムラインフレーム / プレイヘッドを設定します — ある時点にジャンプし、後続のクック、スナップショット、エクスポート、シミュレーション読み取りがそのフレームで評価されるようにします。 | `frame` |
| `set_display` | SOPまたはOBJノードのdisplayおよび/またはrenderフラグを設定します — 何を表示/レンダーするかをクリーンに制御します。 | `node` (+2 optional) |
| `delete_node` | シーンからノード（SOPまたはOBJ）を削除します。 | `node` (+1 optional) |
| `clear_scene` | 破壊的なFile->Newを行わずに/objネットワークをまっさらな状態から始めます。mode='hide'（デフォルト、非破壊的 + 可逆）はすべての/objオブジェクトのdisplayフラグをOFFにするため、ビューポートはクリアされますがノードは残ります。mode='delete'は/objオブジェクトを削除します（破壊的 — 各オブジェクトを削除するのと同じ）。 | 2 optional |
| `save_scene` | Houdiniシーン全体（すべてのノードとネットワーク）を、作業ディレクトリに制限したうえで、ディスク上の.hip / .hipnc / .hiplcプロジェクトファイルに保存 / 書き込みます — 「作業を保存する」/ セッションをスナップショットする操作。 | `path` |
| `select_node` | ノードを選択し（それまでの選択をすべて解除）、カレントノードにします。 | `node` (+1 optional) |
| `frame_selected` | Scene Viewerをノードに合わせてフレーミングします — Shift+Hの「home selected」に相当し、frame-allが役に立たないスケール混在のシーンで正確なフレーミングを行います。 | 1 optional |
| `layout_nodes` | 新しく追加したノードが重ならないように、ネットワークの子ノードを自動整列します — Shift+Lに相当。 | `parent` |
| `find_error_nodes` | 読み取り専用の診断：サブツリーをスキャンしてエラー（およびオプションで警告）状態のノードを探し、AIエージェントが自己修正できるようにそのパス、タイプ、メッセージを報告します。root（デフォルト/obj）がスキャンの範囲を定めます（root自身とそのすべての子孫）。ノードごとにガード付きのクックが試みられるため、壊れたノード（例：存在しないパスを指すFile SOP）は、例外の送出ではなく捕捉されたエラーとして表面化します。 | 2 optional |
| `batch` | 呼び出しごとのレイテンシを削減するため、最大64のツールオペレーションを1回の呼び出しで実行します（例：1回のラウンドトリップでノードチェーンを構築）。 | `ops` (+1 optional) |
| `capabilities` | ここから始めてください — はじめに、本サーバーの使い方、できることの概要、新しいエージェント向けのオリエンテーションと最初のステップ。 | — |
| `node_reference` | 権威ある、ライブプローブされたHoudini 21.0.671ノードリファレンスを照会します — 検証済みのノードタイプとその実際のパラメーター名で、どのようなノードチェーンが可能かの信頼できる情報源。 | 3 optional |
| `vex_reference` | 権威あるオフラインのHoudini 21.0.671 VEXリファレンスを照会します：1073個の組み込み関数（そのままのシグネチャ、要約、ヘルプグループ）に加え、厳選されたラングルのワークフロー/パターンガイド。 | 4 optional |
| `recipe_reference` | 正準的で、ツールに対応付けられたワークフローレシピ — 本サーバーのツールで実際にXを行う方法と、目の前の対象にどのレシピが合うかを選ぶルーター。 | 4 optional |
| `viewport_display` | Scene Viewerの表示/解析オーバーレイ（ポイントマーカー、point/prim/vertexの法線、point/primの番号、ポイント位置、ポイントトレイル）を切り替え、snapshot/capture_uiのスクリーンショットがジオメトリ解析に読み取れるようにします。 | 9 optional |
| `read_geo_stats` | ノードの構造化されたジオメトリ統計を読み戻します — point/primitive/vertexの数、バウンディングボックス（min/max/size/center）、およびpoint/prim/vertex/detailの全アトリビュートとその型の一覧を、高速なintrinsicsを介して取得します（マルチGBのポイントクラウドでも安全。ポイントごとのPythonループはありません）。 | `node` (+1 optional) |
| `isolate` | ポイントクラウドを関心領域にクロップします：向きを持つクロップボックスオブジェクトの内側に入るポイントだけを残し（box OBJ自身のワールドトランスフォームを使うため、回転したボックスは向きを持つボリュームをクロップします）、残りを削除します — スキャンを1つの建物/部屋/エリアに切り詰めます。box = クロップ境界として機能するbox OBJ。outはオプションで、クロップされたクラウドを制限された.bgeo/.plyに書き出します。 | `input`, `box` (+1 optional) |
| `object_merge` | 1つまたは複数の他のSOP / OBJジオメトリストリームを、ジオメトリをコピーせずにパスでネットワークに参照 / インポート / 取り込みます — 大規模シーン、会場、複数オブジェクトのアセンブリ用プリミティブ（多数のオブジェクトを1つにまとめる / 結合する / 集める / シーン内の別の場所からジオメトリをインスタンスする。何も複製しないため巨大シーンでも耐えます）。 | `sources` (+7 optional) |
| `subnet_organize` | ノードグラフを整理 / 整頓 / クリーンアップします（データ専用、クックなし、ジオメトリ変更なし）：op=collapseは一連の兄弟ノードをサブネットにまとめます（ノードをグループ化）。op=createは空のサブネットコンテナを作成します。op=tagはノードにネットワークエディターの色、コメント/ノート、および/またはuser-dataのkey/valueを付与し、組み上げたグラフをナビゲート可能で読みやすくします。 | 9 optional |
| `matchsize` | ジオメトリ入力を、リファレンスのバウンディングボックスまたは明示的なターゲットサイズに合わせてフィット / リサイズ / 再スケール / 再配置 / 整列します — 「このアセットを正しいサイズと位置でシーンに配置する」/「正規化 / スナップ・トゥ・バウンズ」を行う型付きノード（matchsize SOP）。 | `input` (+9 optional) |
| `scene_assemble` | 1コールでステージングされた複数ピースのシーンアセンブリ / コンポジションマクロ（会場ポートフォリオ用プリミティブ）：多数のソースジオメトリから、ナビゲート可能な組み上げ済みシーン全体を、まっさらな1つの/obj geoの中に構築します。 | `name`, `pieces` (+2 optional) |
| `list_node_types` | 利用可能なHoudiniノードタイプのパレットを発見 / 列挙 / 検索します — どのオペレーター（SOP/OBJ/LOP/DOP/COP/ROP/VOP/...）タイプが名前で存在するか、カテゴリーごとの件数付きで示します。 | 3 optional |
| `reload_node` | ノードにソースファイルをディスクから再読み込みさせ、リフレッシュ / 再クックさせます — File SOPの.bgeo/.obj（またはキャッシュされた任意のファイル）が外部で書き換えられた後に使用し、Houdiniが新しい内容を取り込むようにします。 | `node` |
| `mem` | プロセスのワーキングセット + システムRAM + Houdiniメモリ + GPU VRAM（カード全体のtotal/used/avail — フリーズ上限のシグナル）を報告します。自己監視とメモリを踏まえたオペレーションのサイジングのために：メモリが不足していないか、VRAM / GPUメモリの余裕はどれだけ残っているか、メモリ予算はいくらか、フリーズするまであとどれだけ構築できるか。 | — |
| `viewport_snap` | Scene Viewerのスナッピングを設定 / 構成します — グリッドへのスナップ、points / prims / geometry / templates / 他のオブジェクト / guides / drawablesへのスナップ。 | 6 optional |
| `view_message` | Scene Viewerにオペレーター向けのメッセージ（通知、画面上のトースト、ステータスラインのプロンプト）を表示 / フラッシュします — エージェントが何をしているかを人間に伝えるための、見守るクルー向けUX。type=flashは一時的なオーバーレイ（duration秒）。type=promptは指定した深刻度レベルで永続的なステータスラインのプロンプトを設定します。 | `message` (+3 optional) |
| `home_view` | 現在のビューポートを、ターゲット（all \| selected \| grid \| non_templated）に対するデフォルトのビュー方向へホーム / リセット / 再センタリング / フレームオールします — frame_selectedとは異なり、こちらは現在のビュー方向を保持します（frame_selectedは再フレーミングしますが現在のビュー方向を保持します）。 | 1 optional |
| `save_view_to_camera` | 現在のインタラクティブなビューポートビュー（トランスフォーム + レンズ設定）をカメラOBJノードにベイク / 保存します — 「save view to camera」/ このビューからカメラを作成する。 | `camera` (+1 optional) |
| `construction_plane` | Scene Viewerのconstruction-planeグリッドを表示 / 非表示 / リサイズします — 可視性、セルサイズ、セル数、ルーラーライン当たりのセル数。 | 4 optional |
| `ui_reference` | 読み取り専用のコントロールサーフェス発見 / ヘルプ（node_reference/vex_referenceの姉妹）：コントロールサーフェスのツールと確認済みの列挙トークンを発見し、GUIが稼働しているときには現在の操作可能なUIの状態（スナッピングモード、construction-planeの可視性、ビューアーステート名、デスクトップ名）を読み取ります。 | 1 optional |
| `switch_desktop` | デスクトップ（ワークスペース / 保存済みのペインレイアウト — Build、Animate、Solaris、…）を名前で切り替え / アクティブ化します。 | `desktop` |
| `pane_focus_node` | パスベースのペイン（parm \| network \| scene）をノードにジャンプ / ナビゲート / 向けます（クイックナビ） — それをペインのカレントノードにします。networkの場合、ノード自身のネットワークにダイブすることもできます。 | `node` (+2 optional) |
| `pane_pin` | パスベースのペインをピン留め / ピン解除（またはそのリンクグループを設定）して、選択の追従を停止させます — parm/network/sceneペインをカレントノードで固定します。 | 3 optional |
| `pane_tab` | ペインのタブをタイプ別に開く / 作成 / 閉じる / 切り替え / 複製 / タイプ変更します（データ専用） — Network Editor / Parameters / Spreadsheet / Detailsのタブを追加する、閉じる、カレントにする。op=queryは有効なpaneTabTypeトークンと現在のタブを一覧します（ペインのID/タイプを発見するため最初に実行）。create/set_type/current/clone/closeはターゲットペインに作用します。 | 3 optional |
| `pane_layout` | 現在のデスクトップのペインレイアウトを分割 / 最大化 / 復元 / 整列します（可逆的なセッションUI） — ペインを水平または垂直に分割する、最大化する、復元する。 | `op` (+1 optional) |
| `network_navigate` | Network Editorをノードグラフの中でナビゲート / ジャンプ / ダイブします — ネットワークにダイブする（path）、ノードを選択してカレントにする（current_node）、および/または選択をフレーミングする（frame）。 | 3 optional |
| `hotkey_reference` | hou.hotkeysから読み取る、読み取り専用のデフォルトホットキー / キーボードショートカットマップリーダー（vex_reference/node_referenceの姉妹） — キーボードショートカットを検索 / 探します：context → command → 割り当てキー + 人間向けラベルを、オプションの検索フィルターまたはカテゴリーモードとともに示します。 | 5 optional |
| `set_node_flags` | 1つのノードのノードフラグを設定 / 切り替えます — display、render、template、bypass、lock、soft-lock、highlight、debug、visible、xray、display-comment、descriptive-name — setGenericFlagを介して行います。 | `node` (+13 optional) |
| `node_organize` | ネットワーク内の1つのノードを整理 / 整頓 / 配置 / ラベル付け / 色分けします — その色、ノードのシェイプ、コメント（表示専用テキスト）、名前（リネーム）、ネットワーク上の位置を設定します。 | `node` (+6 optional) |
| `viewport_appearance` | 視覚的な受け入れ / スクリーンショットのループのためにジオメトリが見えるように、GeometryViewportの表示 / 検査 / シェーディング設定を行います — シェーディング/表示モード（wireframe・shaded・flat・matcap・hidden-line・bounding-box）、point/prim/vertexのマーカー・法線・番号の表示、バックフェース除去、テクスチャ、アンビエントオクルージョン、カラースキーム、ライティング。 | 19 optional |
| `viewport_layout` | Scene Viewerのビューポートレイアウトを設定します — ペインがどのようにビューポートに分割されるか（single \| quad \| double \| tripleのバリアント）。 | `layout` (+1 optional) |
| `enter_state` | 5つの固定された組み込みScene Viewerツールステートのいずれかを名前で開始 / アクティブ化します（構造上データ専用） — view（見回し）\| translate \| rotate \| scale（トランスフォームハンドルのステート）\| current_node（カレントノード自身のツールステート）。 | `state` |
| `viewport_optimize` | 遅い / カクつく / 重いScene Viewerを、表示専用のパフォーマンスレバーを適用して高速化します — ボリューム品質を下げる、シーンのポリゴン表示に上限を設ける、距離ベースのパックドカリングを有効にする、level-of-detailとアンチエイリアシングを下げる。 | 1 optional |
| `rivet` | Rivet OBJ（rivet）を作成します — デフォームするサーフェス上のpoint/primitiveに固定されるトランスフォーム（定番の「アニメーションするメッシュに小道具を貼り付ける」アタッチ）。 | 10 optional |
| `sticky` | Sticky OBJ（sticky）を作成します — サーフェス上のUV座標にピン留めされるトランスフォームで、サーフェスがデフォームするとともにスライドします。 | 11 optional |
| `blend_sticky` | Blend Sticky OBJ（blendsticky）を作成します — 複数のソースstickyオブジェクトの重み付きブレンドで位置が決まるSticky（ソースのstickyをこれにペアレントします）。 | 8 optional |

### パラメーター

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `set_parm` | 1つのノードパラメーターをリテラル値に設定 / 書き込み / 駆動します（リテラルのみで、式は決して使いません） — 汎用のparmセッターに対する安全でデータ専用の対応物。 | `node`, `parm`, `value` (+1 optional) |
| `get_parm` | 1つのノードパラメーター値を読み取り / 取得 / 検査します（読み取り専用、データ専用）：評価済みの値、生の / 展開前の値、parmの型、現在式やキーフレームを保持しているか（その式の文字列とともに）、そして拒否されたコードparmかどうか（注入された式が見えるように）を返します。 | `node`, `parm` (+1 optional) |
| `set_keyframe` | 数値parmをあるフレームでアニメーションさせるために、リテラルの数値 + オプションの許可リスト化された補間（constant / linear / bezier / ease / …）を用いてキーフレームを1つ設定 / 追加します — float / int / toggle / menuのparm向けのリテラル値アニメーション。 | `node`, `parm`, `frame`, `value` (+2 optional) |
| `delete_keyframes` | parmのキーフレームを削除 / クリア / 除去して、静的なリテラル値に戻します（アニメーション解除）。 | `node`, `parm` (+3 optional) |
| `list_keyframes` | parmのキーフレーム / アニメーションの読み取り専用リスト — 各キーフレームのフレーム、リテラル値、補間文字列（例：'bezier()'）を返し、エージェントがアニメーションを検査できます。 | `node`, `parm` (+1 optional) |

### デリバリー＆エクスポート

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `export_geometry` | SOPをクックし、単一のジオメトリファイルに書き込みます（/outの`geometry` ROP。書き込みを実行します）。 | `input`, `output` (+1 optional) |
| `batch_export` | `input`ジオメトリをパーティションに分割し、パーティションごとに制限されたファイルを1つ書き込みます — TDから繰り返し寄せられる要望の第1位（「これをgroup/name/attributeで分割して各ピースをエクスポートして」）。split_by=name（デフォルト）は`name`プリミティブアトリビュートの異なる値ごとに1ファイルを書き込みます。split_by=groupはprimitive/pointグループごとに1ファイルを書き込みます。split_by=attributeは`attribute`で指定したpoint/primアトリビュートの異なる値ごとに1ファイルを書き込みます。 | `input` (+7 optional) |
| `export_pointcloud` | ポイントクラウド / ジオメトリを作業ディレクトリ内のPLYにエクスポートします — import_pointcloud/las_import経由で取り込んだクラウドの出口。 | `input`, `output` (+2 optional) |
| `export_alembic` | SOPをAlembic .abcにエクスポートします（/outの`alembic` ROP。書き込みを実行します） — アニメーション / デフォームするジオメトリをMaya/Nuke/Blender/UEに渡すための標準的な交換形式。frames=[start,end]は単一の.abcにアニメーション付きキャッシュを書き込みます。静的フレームの場合は省略します。format ogawa（モダン、より高速、より小さい — 推奨）\| hdf5（レガシー）\| default。 | `input`, `output` (+3 optional) |
| `capture_ui` | 稼働中のHoudiniインターフェースをスクリーンショット / 閲覧 / 読み取ります。要求に応じて単一のペインに限定します。 | 5 optional |
| `snapshot` | 3Dの結果を閲覧/スクリーンショットします — ビューポート/カメラの単一のOpenGL PNGをツール結果にインラインで返します（image->3D検証のためのエージェントの目）。 | 6 optional |
| `niagara` | SideFX Labs Niagara — 入ってくるパーティクル/ポイント（`input`、input 0）をUnrealのNiagaraシステム向けにパッケージするワイヤー接続のみ（構築はするが実行はユーザーが行う）のエクスポーターSOP。 | `input` (+8 optional) |
| `pcg_export` | SideFX Labs PCG Export — 入ってくるインスタンスポイント（`input`、input 0）をUnrealのPCGフレームワーク向けにパッケージするワイヤー接続のみ（構築はするが実行はユーザーが行う）のエクスポーターSOP。 | `input` (+7 optional) |
| `unreal_groom_export` | SideFX Labs Unreal Groom Export — HoudiniのgroomをUnrealのgroomシステム向けにパッケージし、Alembicとして書き出します。 | 13 optional |
| `unreal_spline` | SideFX Labs Unreal Spline — 入ってくるカーブ（`input`、input 0）をUnrealのスプラインとしてパッケージします。クックされたSOP出力はカーブをそのまま通します（オプションでタグ付き）。orient_along_curveはポイントごとの向きを書き込み、prim_tagsはプリミティブごとのタグを書き込みます。 | `input` (+4 optional) |
| `vector_field` | SideFX Labs Vector Field — 入ってくる速度場（`input`、input 0 — 速度ボリューム、または速度アトリビュートを持つポイント）を均一グリッドに再サンプリングし、Unreal/Unityの.fgaベクトルフィールドエクスポートを準備します。クックされたSOP出力はサンプリングされた場を可視化します。input_typeはvolumes(0)またはpoints(1)を選択します。velocity_volumes/velocity_attrはソースを指定します。divはグリッド解像度の除数を設定します。 | `input` (+9 optional) |
| `niagara_rop` | SideFX Labs Niagara ROP — Niagaraエクスポーターの/out Driver形式：SOPをパス（`soppath`）で参照し、それをUnrealのNiagaraシステム向けに書き出します。 | 6 optional |
| `rbd_to_fbx` | SideFX Labs RBD to FBX — パックされたRBDシミュレーション（`node_to_export`で参照）を、ゲームエンジン向けのリジッドボディFBXとしてエクスポートする/out Driver。 | 9 optional |
| `vertex_animation_textures` | SideFX Labs Vertex Animation Textures — 主力のVATエクスポーター：アニメーションしたSOP（`soppath`で参照）を、Unreal/UnityのVATシェーダー向けに position/rotation/color テクスチャ + ベースメッシュにベイクします。 | 11 optional |
| `xyz_pointcloud_exporter` | SideFX Labs XYZ Pointcloud Exporter — SOPのポイント（`objpath1`で参照）をプレーンテキストのXYZ/CSVポイントクラウドに書き出す/out Driver。 | 3 optional |
| `texture_sheets` | SideFX Labs Texture Sheets — ワイヤー接続のみ（構築はするが実行はユーザーが行う）のテクスチャシート / フリップブックレンダラー（Mantra ROP）。 | 18 optional |
| `goz_export` | SideFX Labs GoZ Export — GoZブリッジを介してジオメトリをZBrushに渡すワイヤー接続のみ（構築はするが実行はユーザーが行う）のエクスポーター。 | `input` (+2 optional) |
| `filecache` | SideFX Labs File Cache — ワイヤー接続のみ（構築はするが実行はユーザーが行う）のジオメトリキャッシュ。 | `input` (+6 optional) |
| `static_fracture_export` | SideFX Labs Static Fracture Export — 破砕されたオブジェクト（`input`）のピース向けのワイヤー接続のみ（構築はするが実行はユーザーが行う）のエクスポーター。 | `input` (+5 optional) |
| `simple_baker` | SideFX Labs Simple Baker — ワイヤー接続のみ（構築はするが実行はユーザーが行う）のマップベイカー。 | `input` (+19 optional) |
| `unreal_pivotpainter` | SideFX Labs Unreal Pivot Painter — UE4/5の風アニメーション向けにpivot / hierarchyテクスチャをベイクするワイヤー接続のみ（構築はするが実行はユーザーが行う）のエクスポーター。 | `input` (+10 optional) |
| `zibravdb_filecache` | SideFX Labs ZibraVDB File Cache — ワイヤー接続のみ（構築はするが実行はユーザーが行う）の圧縮VDBキャッシュ。 | `input` (+3 optional) |
| `rop_zibravdb_compress` | SideFX Labs ROP ZibraVDB Compress — ワイヤー接続のみ（構築はするが実行はユーザーが行う）の圧縮VDB ROP。 | `input` (+3 optional) |
| `games_baker` | SideFX Labs Games Baker — 高解像度のソースメッシュから低解像度のターゲットメッシュへ、HoudiniネイティブのCOP/Karmaベイクを介してテクスチャマップ（basecolor / normal / AO / roughness / metallic / curvature / thickness / position / …）をベイクする/out Driver。 | 40 optional |
| `csv_exporter` | SideFX Labs CSV Exporter — SOPのpoint/primアトリビュート（export_nodeで参照）をプレーンテキストのCSVファイルに書き出す/out Driver。 | 12 optional |
| `json_exporter` | SideFX Labs JSON Exporter — SOPのアトリビュート（export_nodeで参照）をJSONファイルに書き出す/out Driver。 | 5 optional |
| `export_usd` | LOPネットワークからUSDステージを、制限された出力パスに書き込みます（/outの`usd` ROP。書き込みを実行します）。 | `output` (+3 optional) |
| `export_fbx` | `input`を含むOBJからFBX（.fbx）を、制限された出力パスに書き込みます（/outの`filmboxfbx` ROP。書き込みを実行します） — Maya/Max/UE/Unity向けの、リグ付き / アニメーション付き交換の標準形式。 | `input`, `output` (+2 optional) |
| `export_gltf` | `input`SOPからglTF/GLBを、制限された出力パスに書き込みます（/outの`gltf` ROP。書き込みを実行します） — ウェブ / リアルタイム向けの交換形式（three.js、model-viewer、UE/Unity、AR quicklook）。exporttype auto（拡張子から — デフォルト）\| gltf（.gltf + 外部バッファ）\| glb（単一ファイルのバイナリ）。frames=[start,end]はアニメーション付きglTFを書き込みます。静的フレームの場合は省略します。 | `input`, `output` (+3 optional) |
| `export_cache` | バージョン管理されたジオメトリキャッシュ — フレームごとの.bgeo.scシーケンス — をフレーム範囲にわたって書き込みます（/outの`geometry` ROP。書き込みを実行します）。 | `input`, `output` (+2 optional) |
| `flipbook` | 高速なOpenGLプレビューシーケンスをレンダーします（/outの`opengl` ROP。書き込みを実行します） — モーションを確認するためのビューポート品質のフリップブックであり、最終レンダーではありません（最終レンダーにはsetup_karma/karma_render_settingsを使用してください）。 | `output` (+5 optional) |
| `export_package` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）のステージング済みUSDエクスポート / 受け渡し / パッケージ書き込み：組み上げたLOPステージを制限された.usd/.usda/.usdc/.usdzファイルに書き出す`usd` ROP（Driver）を構築して完全に構成しますが、実行はしません — setup_karma / bake_textureと同様に、ステージ全体のフラット化は重い書き込みになりうるため、呼び出し側/人間が実行します（rendered=falseを返します）。 | `loppath`, `output` (+3 optional) |
| `define_hda` | 既存のSOPサブネットを、再利用可能でパス制限されたHoudini Digital Assetにパッケージします — 「このネットワークを再利用可能なツールにする」操作。 | `node`, `output`, `type_name` (+6 optional) |
| `usd_export_sop` | `input`SOPのジオメトリをUSDファイルに書き込みます（SOPコンテキストの`usdexport` — ネイティブSOPからUSDステージへの書き込みブリッジ。書き込みを実行します）。outputは作業ディレクトリにrealpathで書き込み制限されます。拡張子でフォーマット（.usd/.usda/.usdc/.usdz）を判定します。 | `input`, `output` (+8 optional) |
| `usd_stitch` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：複数の入力USDレイヤーを出力レイヤーに統合するUSD Stitch ROP（/out usdstitch）を構築します — 構成はされますが決して実行されません（書き込みはユーザーが実行）。 | `input_files`, `output` (+1 optional) |
| `usd_stitch_clips` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：フレームごとのUSDクリップをvalue-clipのトポロジー + テンプレートに組み上げるUSD Stitch Clips ROP（/out usdstitchclips）を構築します — 構成はされますが決して実行されません。 | `input_files`, `output_template` (+5 optional) |
| `usd_zip` | ワイヤー接続のみ（構築はするが実行はユーザーが行う）：入力USDレイヤーを.usdzアーカイブにパッケージするUSD Zip ROP（/out usdzip）を構築します — 構成はされますが決して実行されません。 | `input_files`, `output` (+2 optional) |

### レンダー＆出力（ワイヤー接続のみ）

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `render_mantra` | Mantra CPU画像レンダーROP（ifd、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにMantraレンダーを構築・配線します。実行はユーザーが行います。 | 11 optional |
| `render_karma_rop` | DriverコンテキストのKarma画像レンダーROP（karma、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにKarmaレンダーを構築・配線します。実行はユーザーが行います。 | 11 optional |
| `render_usd` | DriverコンテキストのUSD/HuskレンダーROP（usdrender、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにHuskレンダーを構築・配線します。実行はユーザーが行います。 | 10 optional |
| `render_comp` | コンポジット/COPネットワークの画像書き込みROP（comp、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにコンポジット書き込みを構築・配線します。実行はユーザーが行います。 | 8 optional |
| `render_image` | COP画像レンダーROP（image、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにCOP画像書き込みを構築・配線します。実行はユーザーが行います。 | 8 optional |
| `export_ifd_archive` | Mantra IFDシーンアーカイブエクスポートROP（ifdarchive、out/） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにアーカイブエクスポートを構築・配線します。実行はユーザーが行います。 | 7 optional |
| `render_settings_usd` | USD RenderSettings prim（Solaris rendersettings LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：下流のレンダラーが読み取るトップレベルのレンダー設定（解像度、サンプル数、カメラ）を構築・配線します。レンダーの実行はユーザーが行います。 | 7 optional |
| `render_product` | USD RenderProduct prim（Solaris renderproduct LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：レンダラーが書き込む出力画像（パス、タイプ、フレーミング）を指定します。レンダーの実行はユーザーが行います。 | 7 optional |
| `render_var` | USD RenderVar / AOV定義（Solaris rendervar[::2.0] LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：レンダラーが生成する1つのAOV / レンダー出力変数（source + データ型）を宣言します。 | 6 optional |
| `render_vars_additional` | 追加のRenderVar（Solaris additionalrendervars LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ステージのレンダー出力セットに、AOV / RenderVarの行を1つ追加します。 | 7 optional |
| `karma_render_properties` | Karma Render Properties（Solaris karmarenderproperties LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ステージ上にKarmaのレンダー設定 + プロダクト構成を組み合わせて構築・配線します。レンダーの実行はユーザーが行います。 | 9 optional |
| `karma_render_products` | Karma Render Productsバンドル（Solaris karmarenderproducts[::2.0] LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ステージ上にKarma出力プロダクトのセット（beauty + AOV）を構築・配線します。レンダーの実行はユーザーが行います。 | 7 optional |
| `karma_render_vars` | Karma Standard RenderVars（Solaris karmastandardrendervars[::2.0] LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ステージ上に標準のKarma AOVセット（beauty、diffuse/glossy/volumeの分割など）を構築・配線します。レンダーの実行はユーザーが行います。 | 4 optional |
| `karma_cryptomatte` | Karma Cryptomatte AOVセットアップ（Solaris karmacryptomatte LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：ステージ上にcryptomatteのIDマット出力を構築・配線します。レンダーの実行はユーザーが行います。 | 5 optional |
| `husk_image_metadata` | Husk Image Metadata（Solaris huskimagemetadata LOP） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：レンダー出力画像にメタデータ（どのprimのアトリビュートを埋め込むか）を構築・配線します。レンダーの実行はユーザーが行います。 | 3 optional |
| `rop_geometryraw` | ROP Geometry Output — RAW（`rop_geometryraw`、SOPコンテキスト） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：`input`の後のSOPネットワーク内にraw-geometryエクスポートROPを構築・配線します。書き込みの実行はユーザーが行います。 | `input` (+4 optional) |
| `dopio` | DOP I/O（`dopio`、SOPコンテキスト） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：DOPのフィールド/ジオメトリのディスクキャッシュノードを構築します（SOP入力なし — DOPネットワークをパスで参照してファイルを書き込みます）。キャッシュの実行はユーザーが行います。 | 6 optional |
| `heightfield_output` | Heightfield Output（`heightfield_output`、SOPコンテキスト） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：`input`の後にハイトフィールド/地形のheightmapエクスポートROPを構築・配線します。書き込みの実行はユーザーが行います。 | `input` (+8 optional) |
| `export_channel` | CHOPチャンネル/モーションエクスポートROP（channel、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：CHOPチャンネル/モーションのエクスポーターを構築・配線します。実行はユーザーが行います。choppathはシーンのCHOPパス（データ）。output -> chopoutput（制限）。 | 7 optional |
| `export_mdd` | MDDポイントキャッシュエクスポートROP（mdd、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：MDDポイントキャッシュのエクスポーターを構築・配線します。実行はユーザーが行います。soppathはシーンのSOPパス（データ）。output -> file（制限）。 | 8 optional |
| `render_dsm_merge` | Deep-Shadow-MapマージROP（dsmmerge、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：DSMマージを構築・配線します。実行はユーザーが行います。output -> dsm_output（書き込み制限）。dsm_source1/2は読み取り制限された入力。 | 8 optional |
| `export_brickmap` | Brick-mapジェネレーターROP（brickmap、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：point-cloud/i3d -> brick-mapのジェネレーターを構築・配線します。実行はユーザーが行います。sopはシーンのSOPパス（データ）。output/geofile/ptcfile/i3dfileは制限されます。 | 9 optional |
| `bake_animation_rop` | Bake Animation ROP（bake_animation、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：オブジェクトアニメーションをキーフレーム/CHOPチャンネルにベイクする処理を構築・配線します。実行はユーザーが行います。sourceとwrite_to_chop_channelはシーンデータ（そのまま）。 | 7 optional |
| `export_geometry_raw` | Raw geometry stream ROP（geometryraw、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：raw geometry streamのダンプを構築・配線します。実行はユーザーが行います。soppathはシーンのSOPパス（データ）。output -> sopoutput（制限）。 | 7 optional |
| `export_ml_example_raw` | ML Example Raw ROP（ml_exampleraw、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：rawなML学習サンプルのエクスポーターを構築・配線します。実行はユーザーが行います。soppathはシーンのSOPパス（データ）。output -> sopoutput（制限）。 | 9 optional |
| `export_ml_example_output` | ML Example Output ROP（ml_exampleoutput、SOPコンテキスト） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：SOP（input 0）の後にML例データセットのライターを構築・配線します。実行はユーザーが行います。output -> sopoutput（制限）。 | `input` (+4 optional) |
| `export_ml_example_raw_sop` | ROP ML Example Raw（rop_ml_exampleraw、SOPコンテキスト） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：SOP（input 0）の後にSOPレベルのraw ML例エクスポーターを構築・配線します。実行はユーザーが行います。soppathはシーンデータ。output -> sopoutput（制限）。 | `input` (+9 optional) |
| `render_ml_cv_synthetics` | Labs ML-CV Synthetics Karma ROP v1.0（labs::ml_cv_synthetics_karma_rop::1.0、lop/Solaris） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/stageにKarmaの合成データレンダラー（beauty + 大規模なAOVセット）を構築・配線します。レンダーの実行はユーザーが行います。camera/primpath/primpatternはUSDシーングラフのデータ。画像出力は制限されます。res/samples/framesはクランプされます。レンダーボタンは決して押されません。 | 16 optional |
| `render_ml_cv_synthetics_v11` | Labs ML-CV Synthetics Karma ROP v1.1（labs::ml_cv_synthetics_karma_rop::1.1、lop/Solaris） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：::1.1アセット（入力2つ。importsecondaryinputvars）に対してrender_ml_cv_syntheticsと同じ姿勢です。camera/primpath/primpatternはUSDデータ。画像出力は制限されます。res/samples/framesはクランプされます。レンダーボタンは決して押されません。 | 16 optional |
| `bake_karma_texture` | Karma Texture Baker（karmatexturebaker、lop/Solaris） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/stageにKarmaのUV/テクスチャベイクを構築・配線して構成します。ベイクの実行はユーザーが行います。 | 26 optional |
| `bake_impostor_texture` | Labs Impostor Texture（labs::impostor_texture、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outに八面体インポスターアトラスのベイカーを構築・配線します。ベイクの実行はユーザーが行います。source_geo/camera_rigはシーンのノードパス。output_sequence/anim_output_sequence/sopoutputは制限されます。sprite res + ray-samplesはクランプされます。execute/renderdialogは決して押されません。 | 24 optional |
| `bake_motion_vectors` | Labs Motion Vectors（labs::motion_vectors、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにモーションベクトルアトラスのベイカーを構築・配線します。ベイクの実行はユーザーが行います。export_node/cameraはシーンのノードパス。vm_pictureは制限されます。atlas res + フレーム範囲はクランプされます。execute/render_map/render_sequence/renderdialogは決して押されません。 | 10 optional |
| `bake_flipbook_textures` | Labs Flipbook Textures（labs::flipbook_textures::1.0、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにフリップブックのテクスチャシートベイカーを構築・配線します。ベイクの実行はユーザーが行います。 | 23 optional |
| `bake_haircard_texture` | Hair Card Texture（haircardtex、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにヘアカードのテクスチャベイカーを構築・配線します。ベイクの実行はユーザーが行います。hairobjectsはオブジェクトバンドル、cameraはシーンのノードパス。vm_pictureは制限されます。マップごとの名前トークンはサニタイズされます。res/samplesはクランプされます。execute/renderdialogは決して押されません。 | 23 optional |
| `export_geo_to_i3d` | Geometry to i3d（geo2i3d、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにgeometry->i3dのボリュームテクスチャエクスポートを構築・配線します。実行はユーザーが行います。filename（出力）とimage（入力、読み取り）は制限されます。res/フレーム範囲はクランプされます。execute/renderdialogは決して押されません。 | 19 optional |
| `export_image_to_i3d` | 3D Texture Generator（image3d、out/Driver） — ワイヤー接続のみ（構築はするが実行はユーザーが行う）：/outにi3dの3Dテクスチャジェネレーターを構築・配線します。実行はユーザーが行います。soppath/shoppathはシーンのノードパス。画像出力は制限されます。compressトークンはサニタイズされます。res/samples/フレーム範囲はクランプされます。execute/renderpreview/renderdialogは決して押されません。 | 27 optional |

<!-- END TOOLS (generated) -->

---

## リファレンス

ツールカタログを支える発見用の面が4つあります。`capabilities`はここから始めるべきインデックスであり — 他のすべてへのポインター（稼働中のヘルプサーバーのURLを含む）を出力するため、迷ったらまずこれを呼び出してください。

- **ツールカタログ** — すべての型付きオペレーションを列挙したリスト（`reference/catalog.json`が正式なカウント）で、上記の表として提示されます。パラメーターごとの詳細は`node_reference` MCPツールと`reference/NODE_REFERENCE.md`から得られます。これが*まさに*セキュリティ境界です：カタログになければ、サーバーはそれを実行できません。
- **ノードリファレンス** — `node_reference` MCPツールは「ノードXはどのパラメーターを取るか？」に、ライブでプローブしたグラウンドトゥルースから答えます。人間が読める形のアーカイブは`reference/NODE_REFERENCE.md`（SOP／OBJ／LOP／Driver／COP）で、各ノードをどのツールが公開しているかが注記されています。
- **VEXリファレンス** — `vex_reference` MCPツールは検証済みの安全なVEX関数を検索します。キュレーションされたガイドは`reference/VEX_REFERENCE.md`です。
- **オフラインHoudiniヘルプサーバー** — SideFXの完全なノード／VEX／HOMドキュメントをローカルで提供し、ブリッジと一緒に起動します。MCPツールはありません。`capabilities`の出力がそのURLを表示します。

---

## 実世界の地理空間データ

これが差別化要因です。`acquire_terrain`は唯一のネットワークオペレーションです — 緯度／経度（＋半径）または明示的なバウンディングボックスを渡すと、ソースを自動選択し、取得し、再投影し、Houdiniですぐに使えるタイルを作業ディレクトリに準備します。カバレッジはグローバルです（全マトリクスは[`DOWNLOADER_SCOPE.md`](DOWNLOADER_SCOPE.md)を参照）：

- **US** — USGS 3DEP（1 m lidar／10 m／30 m）に加え、いくつかの州のlidarポータル。
- **グローバル30 m** — Copernicus GLO-30、SRTM、またはJAXA ALOS AW3D30（いずれも匿名、キー不要）。したがって地球上のどの地点でも地形が返されます。
- **各国の高解像度** — オランダ0.5 m、UK 1 m、フランス1 m／0.5 m、スペイン5 m、オーストラリア5 m（「large」／高解像度の要求が対象国内に完全に収まる場合に自動選択）。
- **キー付きオプトイン** — OpenTopographyのグローバルAPIで、ユーザー自身の無料キー（`HMCP_OPENTOPO_KEY`）を使用します。決して同梱されません。

2つの配置モード：

- **flat** — 単一サイト向けのローカルなメートル法ハイトフィールドで、`import_heightfield`により真の標高でインポートします。
- **globe** — WGS84グローブ上にピン留めされたECEFタイル（`build_globe`＋`import_ecef_tile`）。スキャンが正しい地球フレームに収まり、隣接するタイルが構造上レジストレーションされます。

1つのプロジェクト原点が呼び出しをまたいで保持されるため、連続するタイルはフレームを共有し、自動的に整列します。取得は信頼できるDEMホストの小さな集合に制限されます。任意のURLが境界を越えることはありません。

### 座標の規約

```
1 Houdini unit = 1 meter
Working CRS    = a local UTM zone chosen per project (metric, minimal distortion)
X = east-west,  Y = elevation (up),  Z = north-south, NEGATED (north = -Z)
```

**Zの反転**は古典的なミラーの罠です — これでデバッグセッションを丸ごと1回費やしました。1つの原点がプロジェクトごとに保持されるため、連続するタイルはフレームを共有し、自動的に整列します。準備された`<tile>.npy`には、その隣に`<tile>.npy.json`サイドカー（`cols`、`rows`、`res_m`、`houdini_center_x/z`、`nodata`）が必要です。

---

## 落とし穴 — Houdini 21.0.671

Houdiniにおける実世界のLIDAR／DEMは、分かりにくい形で破綻します。以下は21.0.671で確認済みであり、本プロジェクトが苦労して得た本来の価値です：

- **GeoTIFFはHoudiniのCOP2／`heightfield_file`では読み込めません。** すべてのGeoTIFFのI/OはシステムPython（rasterio）→`.npy`で行われ、Houdiniに渡るのは配列のみです。
- **`convertheightfield`は旧式の`createVolume`ボリュームからは0プリミティブを生成します** — しかし適切な`heightfield` SOPボリュームからはクリーンに変換します（検証済み：デフォルトのハイトフィールドから249kポリゴン）。
- **`heightfield_mosaic`／`heightfield_wrangle`はH21には存在しません** — 代わりに`heightfield_patch`／`volumewrangle`を使用してください。
- **「12 GBフリーズ」はビューポートのGLテッセレーションであって、RAMではありません。** 重いハイトフィールドはGPU上で数億のボクセルをテッセレートします。対処法：ディスプレイをOFFにして構築し、ボックスプロキシでパックタイルをストリームし、ボリューム品質を下げます（`viewport_optimize`）。データのRAMは問題になりません。
- **重いハイトフィールドシーンを決してフリップブックやOpenGLレンダーしないでください** — Houdiniがハングする可能性があります。代わりに`capture_ui`（OSレベルのスクリーンキャプチャ）を使用してください。
- **`heightfield` SOPボリュームにはプリミティブアトリビュート`name='height'`が必要です。** また、LIDAR配列は北の行が先頭のため、`setAllVoxels`の前に行を反転します。
- **GLビューポートはPrincipled Shaderのバンプを表示しません**（Karmaレンダーのみ）。本物の起伏にはジオメトリのディスプレイスメントが必要です。

---

## オプション：AMD GPUレンダリング（ProRender）

HoudiniのKarma XPU GPUパスはNVIDIA／OptiX専用です。**AMD Radeon**カード（RDNA2／gfx1030+）を持っていてGPUレンダリングを望む場合、本リポジトリには**AMD Radeon ProRenderの`hdRpr`デリゲートをHoudini 21／USD 25に移植したソースからのビルド**が含まれています — AMDはH21向けのビルド済みプラグインを提供していません。SolarisにネイティブなHydraレンダラー（「RPR」）としてインストールされ、完全にオプションであり、コアMCPからは独立しています。

**状態：動作中**（MSVC **v143**ツールセットで再ビルド。「RPR」は選択可能なHydraレンダラーであり、RPRのマテリアルVOP／LOPのレンダー設定／Material Libraryがすべてロードされます）。既知の利便性上のギャップが1つ：RPRメニューの**Render Devices**ダイアログはまだUSD-25のPythonバインディング移植を必要とします — レンダーには不要です。ビルド済みリリース、ソースからのビルド手順、移植パッチについては**[AMDProRender/README.md](AMDProRender/README.md)**を参照してください。

---

## 設定

ほとんどの設定はGUIで行われ、両方の半分がライブで読み込む共有設定ファイルに書き込まれます。MCPクライアントが必要とする環境変数は、ヘッドレスフラグだけです。

| 設定 | 場所 | 説明 |
|---|---|---|
| `HMCP_GW_HEADLESS` | env（クライアント設定） | `1` = バイナリをヘッドレスstdio MCPゲートウェイとして実行；未設定 = GUIウィンドウを開く。 |
| `HMCP_MIN_ACTION_INTERVAL_MS` | env（クライアント設定） | アクションスロットル（デフォルト`0` = 無効）。設定すると、ゲートウェイは連続する**破壊的な**ツール呼び出し（`delete_node`、`save_scene`、`delete_keyframes`）の間に、ミリ秒単位のこの最小実時間の間隔を強制します — 短いスリープで*ペースを整える*だけで、決して拒否しません。暴走ループやプロンプトインジェクションがシーンを破壊する呼び出しを連射できないようにする安全ガバナーです。非破壊的なツール（構築、読み取り）は決して遅延されません。 |
| 作業ディレクトリ | GUI → Working dir | プロジェクトのルート。すべてのファイルの読み書きはその配下に`realpath`で制限されます。変更＋**Apply**でライブに反映され、再起動は不要です。 |
| Executor port | GUI → Settings | ゲートウェイとHoudini内エグゼキューターが共有するループバックポート。 |
| Session token | GUI → Settings | ゲートウェイとエグゼキューターの間の共有シークレット。自動生成されます。 |
| Auto-arm Houdini | GUI → Settings | HoudiniのGUI起動時にエグゼキューターを自動的にarmします。 |

---

## セキュリティ

セキュリティモデルは、サンドボックスではなく**境界そのもの**です：

- **構造上データ専用。** 任意コード、汎用ノードドライバー、生のVEXやPythonがHoudiniに到達することは決してありません。カタログが攻撃対象領域であり、そのカタログはデータ型のオペレーションです。RCEプリミティブ（`exec`／`node_op`／`wrangle`）がカタログに決して現れないことを、退行テストがアサートします。
- **`realpath`で制限された作業ディレクトリ。** すべてのファイルオペレーションは1つのルートに対して解決され再チェックされ、シンボリックリンク／ジャンクションによる脱出は塞がれています。読み取りはルート配下に存在しなければならず、書き込みは新しいリーフを作成できますが、決して脱出しません。
- **フェイルクローズなarming。** エグゼキューターは、ファイアウォールルールがそのループバックポートへのインバウンド接続をブロックしていない限り、armを拒否します（ステップ4参照）。
- **レンダーはワイヤー接続のみ。** `setup_karma`と`bake_texture`はグラフを構築しますが、決して実行しません — 実行はHoudini内でユーザーが行います。
- **`batch`は権限を付与しません。** `batch`メタツールはレイテンシを削減するために1回の呼び出しで最大64オペレーションを実行しますが、各オペレーションは直接呼び出しと*まったく同一*の経路でディスパッチされます — スキーマ検証、数値のクランプ、ファイルシステムパスの`realpath`制限、そして順序付きの監査。バッチが呼び出せるのは実在するカタログツールだけであり（任意コードやカタログ外の名前は不可）、**ネストできません**（`batch`という名前のオペレーションは拒否されます）。これはレイテンシのエンベロープであって、境界を回避する手段ではありません。
- **オプションのアクションスロットル。** `HMCP_MIN_ACTION_INTERVAL_MS`（デフォルトで無効）は、破壊的なツール（`delete_node`、`save_scene`、`delete_keyframes`）を短いスリープでペースを整え、暴走やインジェクションがシーンの破壊を連射できないようにします。遅くするだけで、決してブロックしません。通常のツールは影響を受けません（設定を参照）。
- **Houdiniの埋め込みPythonはサンドボックス化されていません。** そのため保証されるのは、ゲートウェイで検証される*AIが要求できるもの*であって、プロセスの分離ではありません。AIを準信頼の入力として扱ってください。
- **想定される体制：ループバック、単一の信頼できるユーザー、信頼できるマシン。** これはローカルツールです。トランスポートはローカルホスト上に留まることが意図されています。

コードレベルの監査により、データ専用の境界が構築されたとおりに保たれていることが確認されています。完全な脅威モデル、現在の強化状況、既知の残存項目については[SECURITY.md](SECURITY.md)を参照してください — 単一の信頼できるマシン以外で実行する前に、必ずお読みください。

---

## トラブルシューティング

詳細な解決策については[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)を、日常的な操作については[docs/GUIDE.md](docs/GUIDE.md)を参照してください。

クイックチェックリスト：

- GUIのステータスピルがHoudiniのバージョンとともに**Armed**と表示されている。
- Houdiniがパッケージのインストール*後*に起動され、auto-armが有効になっている。
- ファイアウォール強化ステップ（ステップ4）が実行されている — それがないとエグゼキューターはフェイルクローズです。
- MCPクライアント設定が、ビルドされた`houdini-bridge-mcp.exe`を`HMCP_GW_HEADLESS`を`1`に設定して指している。
- クライアント設定のパスが**バックスラッシュを2つ**使用している（`C:\\...`）。
- 設定を編集した後、クライアントを完全に再起動した。
- ツールに渡すファイルパスが、設定された作業ディレクトリの**内側**にある。

---

## ライセンス

デュアルライセンスです。**非商用利用は無償** — 個人、教育、研究、評価目的での利用は、[PolyForm Noncommercial License 1.0.0](LICENSE)の下で自由に使用できます。**商用、業務、本番での利用には有償ライセンスが必要です**。取得については[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)を参照してください。

このツールは標高データを**一切**同梱しません — 実行時にユーザーに代わってダウンロードします。グローバルソースはパブリックドメイン／オープンです（USGS 3DEP、Copernicus、SRTM、JAXA AW3D30）。各国の高解像度ソースは、それぞれのオープンライセンスの下で帰属表示が必要です（オランダAHN＆スペインIGN — CC-BY 4.0；UK EA — OGL；フランスIGN — Etalab OL 2.0；オーストラリアGA — CC-BY 4.0）。ソースごとのライセンス／帰属表示については[DOWNLOADER_SCOPE.md](DOWNLOADER_SCOPE.md)を参照してください。サードパーティの依存関係の告知は、リリース向けに`THIRD-PARTY-LICENSES.md`へ生成されます（[CONTRIBUTING.md](CONTRIBUTING.md)を参照）。

## サポート

これで時間が節約でき、非商用で利用されているなら、投げ銭はいつでも歓迎です — [ko-fi.com/eviscerations](https://ko-fi.com/eviscerations)。任意であり、いかなるライセンスも付与しません。商用利用は[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)でカバーされます。

## 開発とテスト

テストは2つの環境にまたがる3つの層として実行されます（層1〜2はCIで、層3はローカルで）。Houdiniライセンスのないマシンが正直に証明できるものによって分けられています — 完全な手法は[docs/TESTING.md](docs/TESTING.md)を参照してください：

- **クラウドCI（プッシュごと、Houdiniライセンスなし）：** Rustの`cargo test`がゲートウェイのセキュリティ不変条件をゲートします — カタログが任意コードツールを決して公開しないこと、ツール名が一意であること、`confine_path`が`../`、シンボリックリンク、ジャンクションによる脱出を拒否すること。Pythonジョブは、検証済みVEXバリデーターのレッドチームコーパス、`confined_path`のトラバーサル＋シンボリックリンク脱出の境界、**すべてのツールにわたるカタログ↔エグゼキューターのパリティチェック**（各ツールが正確に1つのデータ専用エンドポイントにマップされ、いずれもRCE型ではないこと）、そして**モックHoudiniに対して各ツールのハンドラーを呼び出すconstruct-smoke**を実行してコードの退行を検出します。これらはツール表面が構造的に健全であり、各ハンドラーのコードが実行されることを検証します — ジオメトリのクックは行いません。
- **ローカル（プッシュ前、ライセンス付き`hython`）：** `tests/executor/`の挙動スイートが実際のジオメトリをクックし、退行テストで固定します。`hython tests/executor/run_tests.py`を実行してください。

完全な手法はコントリビューター向けに[docs/TESTING.md](docs/TESTING.md)で文書化されています。

## コントリビュート

プルリクエスト歓迎です — [CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。ここに記載されていないハードウェアやHoudini構成でテストした場合は、結果を添えてIssueを開いてください。
