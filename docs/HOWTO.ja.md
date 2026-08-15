# ハウツー

生きたドキュメント — ツールがテストされるにつれて成長していきます。以下のステップはいずれも型付きで、サンドボックス化され、説明可能なオペレーションであるため、これらのフローはAIに駆動させながらHoudiniを*学ぶ*安全な手段としても機能します。

## インストール（一度きり）

1. ゲートウェイをビルドします：`gateway/`で`cargo build --release`。
2. ゲートウェイGUIを起動 → **Settings → Install Houdini package**（自動armパッケージをHoudiniのユーザー設定ディレクトリへ配置します）。
3. **作業ディレクトリ**をプロジェクトのルートに設定し（その配下のすべてのサブディレクトリが辿れます）、**Auto-arm**をオンにします。
4. ゲートウェイをMCPクライアントに登録し、ヘッドレスモードの`<PATH_TO_REPO>\gateway\target\release\houdini-bridge-mcp.exe`に向けます。

## エグゼキューターのarm

Houdiniを起動します。`~/.houdini-bridge-mcp/arm.json`から自動でarmされます — 手動のシェルスニペットは不要です。GUIのステータスピルには、接続されたHoudiniのバージョンとともに**Armed**が表示されます。

## 作業ディレクトリの変更

GUIの**Working dir**フィールドに新しいルートを入力し、**Apply**をクリックします。`arm.json`に書き込まれ、エグゼキューターとゲートウェイにライブで反映されます — 再起動は不要です。

## DEMタイルから地形を構築

```
import_heightfield(npy="<tile>.npy", name="terrain", display=true)
```
タイルのシーン上の位置に配置された実際のHoudiniハイトフィールドを生成します（Zは反転）。`.npy`に加えて、その`.npy.json`サイドカー（`cols`、`rows`、`res_m`、`houdini_center_x/z`、`nodata`）が作業ディレクトリ内に必要です。

---

## 実践例

実証済みのエンドツーエンドのフローです。すべてのパスは作業ディレクトリ内に制限されます。

### DEM → 色付き・エクスポート可能な地形

```
import_heightfield(npy="<TILE>.npy", name="terrain")
heightfield_visualize(input="terrain")          # auto elevation ramp
convert_heightfield(input="terrain", bake_colors=true)
export_geometry(input="terrain", output="terrain.obj")
```
`import_heightfield`には、`.npy`に加えてその`.npy.json`サイドカー（`cols`、`rows`、`res_m`、`houdini_center_x/z`、`nodata`）が必要です。いずれも作業ディレクトリのルート配下にあり、パスはそこからの相対です。`heightfield_visualize`は標高ランプを自動で適用します。`convert_heightfield`を`bake_colors`付きで使うと、ランプをポイントカラーへベイクするため、エクスポートしたメッシュがそれを保持します。

### 太陽のあるテクスチャ付きの地球儀

```
build_globe(texture="<EQUIRECT>.jpg", bump="<BUMP>.jpg")
add_light(ltype="sun", t=[x,y,z], r=[rx,ry,rz])   # position via t, aim via r
select_node(node="/obj/globe")
frame_selected()
capture_ui()
```
正距円筒図法の`texture`（＋オプションの`bump`）が球体にドレープします。キー付きの太陽の回転が昼夜の境界線（ターミネーター）を生み出します — ビューポートでレンダリングするか高品質ライティングを有効にすると確認できます。

### 検査とナビゲート

- `scene_info`、`read_geo_stats` — シーンに何があるか / ノードのポイント数とプリミティブ数。
- `list_node_types`、`node_reference` — ノードタイプやそのパラメーターを調べます。
- `select_node`（diveあり）、`frame_selected`（選択対象にホーム）、`layout_nodes`（ネットワークを整理）。
- `viewport_display` — ポイント / 法線を切り替え、その後`capture_ui`または`snapshot`で分析します。

### 既存アセットのインポート

すべて作業ディレクトリ内に制限されます：
- `import_geo` — `.obj` / `.bgeo` / `.fbx`
- `import_pointcloud` — `.ply` / `.bgeo`
- `import_alembic` — `.abc`
- `las_import` — ネイティブLIDAR `.las` / `.laz` / `.e57`
- `osm_import` — OpenStreetMapの道路 / 建物 / フットプリント（サイトコンテキスト）
- `trace_raster` — 画像 → カーブ

### ポイントクラウドをクリーンアップ → メッシュ化

```
import_pointcloud(path="<CLOUD>.ply")
point_normals(...)
segment_planar(...)      # or despeckle / level to clean
mesh_pointcloud(...)
export_geometry(input="<meshed>", output="mesh.obj")   # or export_cache(input=..., output=...)
```
まず法線を推定し、クラウドをクリーンアップし（`segment_planar` / `despeckle` / `level`）、その後メッシュ化してエクスポートします。`despeckle`の半径と`mesh_pointcloud`のボクセルサイズを、クラウドの実際の点間隔に合わせてください。そうしないとすべてを間引いてしまいます（Troubleshootingを参照）。

---

## オプション — AMD GPUでのレンダリング（ProRender）

`setup_karma`はKarmaのレンダーグラフを配線しますが、Karma XPUのGPUパスはNVIDIA専用です。**AMD Radeon**（RDNA2 / gfx1030以降）を使用していてGPUレンダリングを行いたい場合は、オプションの[`AMDProRender/`](../AMDProRender/README.md)アドオンが、Houdini 21向けにネイティブビルドされたAMD Radeon ProRenderの`hdRpr`デリゲートをインストールします — その後、Solaris上でGPU Hydraレンダラーとして「RPR」が現れます（`husk --renderer HdRprPlugin`、またはScene Viewerのレンダラーメニュー）。これは中核のツールセットとは独立しており、ここでのコードは不要です。
