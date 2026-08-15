# オペレーターガイド — houdini-bridge-mcp

AIチャット（Claude Desktopまたは任意のMCPエージェント）からこのMCPを操作するための、日常的な運用リファレンスです。
操作方法、各ツールファミリーの役割、よくあるエンドツーエンドのワークフロー、そして運用上の
落とし穴までを扱っており、セッションを即座に生産的に始められます。すべてのステップが型付きで、説明可能で、サンドボックス化された
オペレーションであるため、AIを傍らに置いてHoudiniを*学ぶ*ための低リスクな手段としても役立ちます — 何かを作るよう頼み、
それがどのようにネットワークを配線するかを観察してみてください。初回のインストールとセットアップについては
[README](../README.md)と[docs/SETUP.md](SETUP.md)を、正確なパラメーターについては`node_reference`ツールに
ライブで問い合わせるか、[reference/NODE_REFERENCE.md](../reference/NODE_REFERENCE.md)のパラメーターリファレンスを参照してください。

---

## 操作方法

チャットからMCPツールを呼び出すことで、**ライブのHoudiniシーン**を構築します。役立つ習慣：

- 最初に`scene_info`を呼び出して現在のシーン（hipファイル、フレーム、`/obj`の内容）を確認します。
- このツールは、1つの**作業ディレクトリ**（セットアップ時に設定）内でのみ読み書きできます。データファイルは
  **そのルートからの相対**パスで参照してください — サブフォルダは辿れます（例：`tiles/site_a.npy`）。ルートの
  外にあるものはすべて拒否されます。
- 操作の前に検査を：`read_geo_stats`（数GBのクラウドでも安全なジオメトリの読み出し）、
  `list_node_types` / `node_reference`（存在するノードとそのパラメーター）。
- 結果を*見る*には、`snapshot`（ビューポートのPNG）または`capture_ui`（ライブインターフェースの画面キャプチャ）を使用します。

---

## インストールとarm（一度きりの要約）

詳細な手順は[README](../README.md) / [docs/SETUP.md](SETUP.md)にあります。要約すると：

1. ゲートウェイをビルドします：`gateway/`内で`cargo build --release`。
2. ゲートウェイGUIを起動 → **Settings → Install Houdini package**（auto-armパッケージを
   Houdiniユーザープリファレンスディレクトリにドロップします）。
3. **Working directory**をプロジェクトルートに設定し — その下のすべてのサブディレクトリが辿れます — さらに
   **Auto-arm**をオンにします。
4. ファイアウォール強化ステップ（`scripts/harden-firewall.ps1`、昇格権限で）を実行します — これがないとエグゼキューターの
   armはフェイルクローズになります。
5. ゲートウェイをMCPクライアントに登録し、ビルド済みの`houdini-bridge-mcp.exe`をヘッドレスモード
   （`HMCP_GW_HEADLESS=1`）で指すようにします。

**エグゼキューターをarmする：** Houdiniを起動します。共有設定ファイルから自動的にarmされます — 手動でのシェルスニペットは不要です。
GUIのステータスピルに**Armed**と接続中のHoudiniバージョンが表示されます。

**作業ディレクトリを変更する：** GUIの**Working dir**フィールドに新しいルートを入力して**Apply**をクリックします。
共有設定が書き換えられ、エグゼキューターとゲートウェイにライブで反映されます — 再起動は不要です。

---

## ツールファミリー

- **取得 / インポート** — `acquire_terrain`（ある場所の実世界の標高を取得）、`import_heightfield`
  （準備済みのDEM `.npy` → ハイトボリューム）、`import_pointcloud`、`import_geo`、`import_alembic`、
  `import_ecef_tile`、`las_import`（ネイティブのLAS/LAZ/E57 LIDAR）、`osm_import`（OpenStreetMapの
  道路/建物/フットプリント）、`trace_raster`、`create_geo`。
- **ハイトフィールド / 地形** — 地形の構築、成形、マスク処理：`heightfield_visualize`、`heightfield_erode`
  （オプションでマスクによるゲート）、`heightfield_maskby*`（feature / occlusion / shadow / object / concavity）、
  `heightfield_flatten` / `clip` / `crop` / `patch` / `layer` / `morph` / `fill` / `cutout` / `deform` /
  `tilesplit`、`convert_heightfield`（→ ポリゴン）、`terrain_analysis`、加えてパックドタイルのストリーミング
  （`add_tile_packed`、`set_tile_lod`）。
- **ジオメトリ / モデル** — `transform`、`boolean`、`polyextrude`、`polybevel`、`remesh`、`polyreduce`、
  `create_primitive`、`create_curve`、`deform`、`drape`、`uv`、`merge`、`fuse`、`normals`、
  `facet_smooth_subdiv`、`lod_create`、`set_color`、`select_group`。
- **グループ / アトリビュート** — `group_create`、`group_combine`、`blast`（グループ単位で削除）、`attribute_transfer`
  （近接によるカラー転送）、`attribute_create` / `attribute_promote` / `attribute_delete` /
  `attribute_cast`、`connectivity`、`measure`。
- **クリーンアップ / メッシュ化** — `point_normals`、`segment_planar`、`despeckle`、`level`、`mesh_pointcloud`、
  `mesh_repair`、`polydoctor`、`polyfill`。
- **VDB / ボリューム** — `vdb_from_polygons`、`vdb_from_particles`、`vdb_convert`、`vdb_filter`、
  `convert_volume`。
- **インスタンス / スキャッター** — `scatter`、`scatter_copy`、`copy_to_points`、`instance`、`pack`、`unpack`、
  `biome_scatter`、`tag_radial`。
- **ソルバー / シミュレーション** — 実際のソルバー上に構築された物理スキャフォールド：`sim_rbd`（Bullet）、`sim_flip` / `sim_viscosity`
  （FLIP）、`sim_pop` / `sim_grains`（POP）、`sim_pyro`、`sim_whitewater`、`sim_ripple`、`sim_vellum`
  （Vellum）、`sim_mpm`（MPM）、加えてocean（`ocean_surface` / `ocean_foam` / `ocean_source`）、`cloud`、
  そして`fluid_surface`。`solver`は汎用のSOPフィードバック/タイムループです（物理ソルバーではありません）。
- **ポイントクラウド解析** — `point_normals`、`segment_planar`、`despeckle`、`level`、`isolate`、
  `tag_radial`。
- **Solaris / LOP / USD** — `sop_import`、`usd_import`、`usd_light`、`usd_camera`、`karma_render_settings`
  （ワイヤー接続のみ）。
- **ルック / カメラ / マテリアル** — `add_camera`、`add_light`、`assign_material`、`set_view_camera`、
  `flightcam`、`build_globe`、`setup_karma` / `bake_texture`（ワイヤー接続のみ）。
- **納品 / エクスポート / キャプチャ** — `export_geometry` / `export_usd` / `export_fbx` / `export_gltf` /
  `export_alembic` / `export_cache`、`flipbook`、`snapshot`、`capture_ui`。
- **シーン / ユーティリティ** — `scene_info`、`read_geo_stats`、`list_node_types`、`node_reference`、`set_frame`、
  `set_display`、`select_node`、`frame_selected`、`layout_nodes`、`delete_node`、`save_scene`、`mem`、
  `viewport_display`、`viewport_optimize`、`reload_node`。
- **キャラクターリギング & アニメーション（KineFX）** — `character_skeleton` / `orient_joints` / `configure_joints`
  （スケルトン）、`bone_capture` / `joint_capture_biharmonic` / `capture_layer_paint`（スキンキャプチャ）、
  `joint_deform` / `bone_deform` / `skeleton_deform` / `blend_shapes`（デフォメーション）、`rig_pose` /
  `ik_chains` / `full_body_ik` / `fbik_configure_targets`（ポージング/IK）、`motion_clip*` /
  `motion_mixer_*`（モーションクリップ）、加えてFBX/mocapのI/O（`fbx_character_import`、`mocap_import`、
  `retarget_biped_fbx`） — ファイルI/Oはすべて作業ディレクトリ内に制限されます。
- **クラウド（群衆）** — `crowd_source` / `agent_source`（エージェント）、`crowd_state` / `crowd_transition` /
  `crowd_trigger*`（ステートマシン）、`crowd_motion_path*`（パス駆動の群衆）、`agent_layer*` /
  `agent_clip*`（エージェントのオーサリング）。
- **マッスル & ティッシュ** — `muscle_id` / `franken_muscle`（構築）、`muscle_solidify`（テトラ化）、
  `muscle_deform` / `muscle_flex`（シミュレーション）、`tissue_*` / `skin_*`（FEM/OTISプロパティ + solidify）。
- **COP / イメージコンポジット** — `cop_*`ファミリー：ノイズ/パターンジェネレーター（`cop_fractal_noise`、
  `cop_worley_noise`）、カラー/フィルターオペレーション（`cop_color_correct`、`cop_blur`、`cop_remap`）、PBRマップのベイク
  （`cop_height_to_normal` / `_ao`、`cop_bake_geometry_textures`）、そして`cop_rop_image`（マップをディスクに書き出し）。
- **ML / ONNX** — `onnx_inference`、`ml_regression`、`ml_volume_upres`、`cop_denoise_ai`、そしてML-CVの
  シンセティクスレーン（`ml_cv_*`、`render_ml_cv_synthetics`）。
- **プロシージャル / SideFX-Labs** — 樹木生成（`tree_trunk_generator` / `tree_branch_generator` /
  `quick_basic_tree`、`lsystem`）、バイオーム（`biome_define` / `biome_scatter` / `biome_initialize`）、
  そしてワールドビルディング（`building_generator`、`road_generator`、`osm_buildings`、レシピ経由の`proc_city`）。

---

## よくあるワークフロー

以下のすべてのパスは作業ディレクトリ内に制限されています。

### DEM → 色付き、エクスポート可能な地形

```
import_heightfield(npy="<tile>.npy", name="terrain")
heightfield_visualize(input="terrain")        # auto elevation ramp
convert_heightfield(input="terrain", bake_colors=true)
export_geometry(input="terrain", output="terrain.obj")
```

`import_heightfield`には`.npy`とそのサイドカーの`.npy.json`（`cols`、`rows`、`res_m`、
`houdini_center_x/z`、`nodata`）が必要です。どちらも作業ディレクトリのルート配下に置き、パスはそこからの相対にします。
`heightfield_visualize`は標高ランプを自動的に適用します（その範囲を自動計算します）。
`bake_colors`付きの`convert_heightfield`は、ランプをポイントカラーにベイクするので、エクスポートされたメッシュがそれを保持します。
`export_geometry`はサーバー対応の`.obj`を書き出します（またはUSD/FBX/glTFを使用）。

### 地形を成形 / 風化させる

`heightfield_maskby*`でマスクを構築（slope、features、occlusion、shadow） → そのマスクを使った`heightfield_erode`で
必要な箇所だけを侵食 → 道路、ベンチ、水際線のためにオプションで`heightfield_flatten` / `clip`。
ほとんどの地形関数はマスクレイヤーを読み込むため、**まずマスクを構築してください**。

### 裸地 → 森に覆われた丘陵

LiDARのDEMは裸地（bare-earth）です。マスクを構築（高さ / 傾斜 / 特徴による） → マスクされた領域に`scatter`または`biome_scatter` →
`copy_to_points` / `scatter_copy`でいくつかの樹木モデルをポイント上に配置（均等な間隔 + ノイズ）。
大量の場合はパックドインスタンシングを使い、ビューポートを軽く保ちます。

### ポイントクラウド → クリーンなモデル

```
import_pointcloud(path="<cloud>.ply")
point_normals(...)
segment_planar(...)      # or despeckle / level to classify + clean
mesh_pointcloud(...)
export_geometry(...)     # or export_cache
```

まず法線を推定し、クラウドをクリーンアップ（`segment_planar` / `despeckle` / `level`）してから、メッシュ化してエクスポートします。
`despeckle`の半径と`mesh_pointcloud`のボクセルサイズを、クラウドの実際の間隔に合わせてください。さもないとすべてを
除去してしまいます（トラブルシューティングを参照）。

### 太陽のあるテクスチャ付きの地球儀

```
build_globe(texture="<equirect>.jpg", bump="<bump>.jpg")
add_light(ltype="sun", t=[x,y,z], r=[rx,ry,rz])   # position via t, aim via r
select_node(node="/obj/globe")
frame_selected()
capture_ui()
```

正距円筒図法（equirectangular）の`texture`（オプションで`bump`）が球体にドレープされます。キー付きの太陽の回転が
昼夜の境界線（ターミネーター）を与えます — ビューポートでレンダリングするか、高品質ライティングを有効にして確認してください。

### ルックをセットアップする

`add_camera` + `add_light`（ポイントまたはdome/HDRI） + `assign_material` → `setup_karma`（レンダーグラフを
配線します。レンダリングはHoudiniで行います） → `snapshot` / `capture_ui`で確認。

### 検査 & ナビゲート

- `scene_info`、`read_geo_stats` — シーンにあるもの / ノードのポイント数とプリミティブ数。
- `list_node_types`、`node_reference` — ノードタイプまたはそのパラメーターを調べる。
- `select_node`（diveあり）、`frame_selected`（選択にホーム）、`layout_nodes`（ネットワークを整える）。
- `viewport_display` — ポイント / 法線の表示切り替え。その後`capture_ui`または`snapshot`で解析。

### 既存アセットのインポート

- `import_geo` — `.obj` / `.bgeo` / `.fbx`
- `import_pointcloud` — `.ply` / `.bgeo`
- `import_alembic` — `.abc`
- `las_import` — ネイティブのLIDAR `.las` / `.laz` / `.e57`
- `osm_import` — OpenStreetMapの道路 / 建物 / フットプリント（敷地のコンテキスト）
- `trace_raster` — 画像 → カーブ

---

## 運用上の落とし穴

- **重い地形はデフォルトで表示オフ** — 大きなハイトフィールドはGPU上で数億個のボクセルをテッセレートし、
  ビューポートを停止させることがあります。意図的に表示させ、大きなシーンでは`viewport_optimize`と`mem`を使い、
  巨大なジオメトリでのフレームオール（全体表示）は避けてください — 代わりに特定のノードを`frame_selected`します。
- **名前の衝突は失敗する** — 作成系ツール（`create_*`、`sim_*`、`scatter_copy`など）は既存のオブジェクトを
  上書きすることを拒否します。新しい名前を使うか、先に`delete_node`してください。
- **数値はクランプされ、拒否されない** — 範囲外の値は許容される最小/最大に固定されるため、奇妙な結果を伴う
  「成功」はクランプされていた可能性があります。
- **`set_display`** はどのノードがビューポートに表示されるかを制御します（1つを設定すると他がクリアされます）。
  **`delete_node`**（`reconnect`あり）はノードを削除し、チェーンを橋渡しして下流が生き残るようにできます。
- **マスクがすべてを駆動する** — ほとんどの地形関数（侵食、スキャッター密度、レイヤリング）はマスクレイヤーを
  読み込むため、まずマスクを構築してください。
- **レンダーはワイヤー接続のみ** — `setup_karma`、`karma_render_settings`、`bake_texture`はグラフを構築しますが
  実行はしません。レンダーはHoudiniで実行します。`export_*`、`flipbook`、`snapshot`、`save_scene`は
  ファイルを*書き出します*。
- **第2入力のオペレーションは同一ジオのオペランドを要する** — `boolean`、`merge`、`drape`、`copy_to_points`は
  異なるジオオブジェクト間では失敗します。両方のオペランドを同じジオに置くか、先に一方をobject-mergeで取り込んでください。
- ツールに渡すファイルパスは**作業ディレクトリ内**にある必要があります。外にあるものはすべて拒否されます。

---

## オプション — AMD GPUでレンダリング（ProRender）

`setup_karma`はKarmaレンダーグラフを配線しますが、Karma XPUのGPUパスはNVIDIA専用です。**AMD Radeon**
（RDNA2 / gfx1030+）では、オプションの[`AMDProRender/`](../AMDProRender/README.md)アドオンが、Houdini 21向けに
ネイティブビルドされたAMD Radeon ProRenderの`hdRpr`デリゲートをインストールします — その後「RPR」がSolarisの
GPU Hydraレンダラーとして表示されます（`husk --renderer HdRprPlugin`、またはScene Viewerのレンダラーメニュー）。
これはコアツールセットから独立しており、ここでのコードは一切不要です。
