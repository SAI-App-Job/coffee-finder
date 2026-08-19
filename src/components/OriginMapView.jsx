import { useState, useRef, useEffect } from "react";
import {
  CONTINENT_PATHS,
  COUNTRY_PATHS,
  COUNTRY_MAP_POSITIONS,
  JAPAN_PATH,
  MAP_INITIAL_VIEWBOX,
  MAP_REGION_PRESETS,
  MAP_MIN_WIDTH,
} from "../data/originMapPaths";

export function OriginMapView({ origins, selected, onSelect }) {
  // 実データ(Natural Earth由来のGeoJSON)をSVGパスに変換して描画している。
  // 大陸の輪郭(CONTINENT_PATHS、薄い色)を背景レイヤーとして敷き、その上に
  // 対象国(COUNTRY_PATHS、強調色)と日本(JAPAN_PATH、現在地の目印)を重ねている。
  // 投影の中心は日本語サイトであることを踏まえ日本を基準にしている(詳細は上記コメント)。
  //
  // 配置にはCSS(Tailwindクラス)を使わず、SVGのviewBox座標系で直接指定している。
  // 以前、Tailwindの任意値クラス(h-[260px]等)が環境によって解釈されず要素が
  // 潰れて見えなくなる不具合が発生したため、座標系がCSSに依存しないSVGへ
  // 全面的に切り替えた。

  const isSelected = (country) => selected?.country === country;
  const svgRef = useRef(null);
  const [viewBox, setViewBox] = useState(MAP_INITIAL_VIEWBOX);

  // wheelイベントはuseEffectでネイティブリスナーとして{ passive: false }で登録する。
  // ReactのonWheel(JSX属性)はデフォルトでパッシブリスナーとして登録されるため、
  // ハンドラ内でpreventDefault()を呼んでもページスクロールを止められない
  // (実際にページスクロールが優先されてしまう不具合が発生したため、この対応が必要だった)。
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const onWheelNative = (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mxRatio = (e.clientX - rect.left) / rect.width;
      const myRatio = (e.clientY - rect.top) / rect.height;

      setViewBox((prev) => {
        const factor = Math.exp(e.deltaY * 0.0015); // 下スクロール=縮小、上スクロール=拡大
        let newW = prev.w * factor;
        newW = Math.min(MAP_INITIAL_VIEWBOX.w, Math.max(MAP_MIN_WIDTH, newW));
        const actualFactor = newW / prev.w;
        const newH = prev.h * actualFactor;

        // カーソル位置のSVG座標を保ったままズームする(カーソル中心ズーム)
        const svgX = prev.x + mxRatio * prev.w;
        const svgY = prev.y + myRatio * prev.h;
        let newX = svgX - mxRatio * newW;
        let newY = svgY - myRatio * newH;

        // 初期表示範囲の外まではパンできないようクランプ
        const minX = MAP_INITIAL_VIEWBOX.x;
        const maxX = MAP_INITIAL_VIEWBOX.x + MAP_INITIAL_VIEWBOX.w - newW;
        const minY = MAP_INITIAL_VIEWBOX.y;
        const maxY = MAP_INITIAL_VIEWBOX.y + MAP_INITIAL_VIEWBOX.h - newH;
        newX = Math.min(Math.max(newX, minX), Math.max(minX, maxX));
        newY = Math.min(Math.max(newY, minY), Math.max(minY, maxY));

        return { x: newX, y: newY, w: newW, h: newH };
      });
    };

    svg.addEventListener("wheel", onWheelNative, { passive: false });
    return () => svg.removeEventListener("wheel", onWheelNative);
  }, []);

  const resetZoom = () => setViewBox(MAP_INITIAL_VIEWBOX);
  const isZoomed = viewBox.w < MAP_INITIAL_VIEWBOX.w - 1;

  // --- ドラッグでのパン操作 -----------------------------------------------
  // dragStateRef: ドラッグ開始時のポインタ位置とその時点のviewBoxを保持(再描画不要な情報)
  // didDragRef: 実際に一定距離動いたかどうか。ピン・国のクリック判定と競合しないよう、
  //             ドラッグ後のクリックはこのフラグを見て握りつぶす。
  const dragStateRef = useRef(null);
  const didDragRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);

  // --- スマホのピンチズーム対応 --------------------------------------------
  // activePointersRef: 現在触れている指(ポインタ)をID→座標で管理する。
  // 2本指になった瞬間にピンチモードへ切り替え、1本指のパンとは別ロジックで
  // viewBoxを更新する。ホイールズーム(PC)とは別経路だが、最終的な
  // viewBox操作(拡大縮小・クランプ)のロジックは共通化している。
  const activePointersRef = useRef(new Map());
  const pinchStateRef = useRef(null);

  const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));

  // ある中心点(SVG座標系の比率)を軸に、指定の倍率でviewBoxを拡大縮小する
  // 共通ロジック。ホイールズーム・ピンチズームの両方から呼び出す。
  const zoomViewBoxAround = (baseViewBox, factor, centerXRatio, centerYRatio) => {
    let newW = baseViewBox.w * factor;
    newW = Math.min(MAP_INITIAL_VIEWBOX.w, Math.max(MAP_MIN_WIDTH, newW));
    const actualFactor = newW / baseViewBox.w;
    const newH = baseViewBox.h * actualFactor;

    const svgX = baseViewBox.x + centerXRatio * baseViewBox.w;
    const svgY = baseViewBox.y + centerYRatio * baseViewBox.h;
    let newX = svgX - centerXRatio * newW;
    let newY = svgY - centerYRatio * newH;

    const minX = MAP_INITIAL_VIEWBOX.x;
    const maxX = MAP_INITIAL_VIEWBOX.x + MAP_INITIAL_VIEWBOX.w - newW;
    const minY = MAP_INITIAL_VIEWBOX.y;
    const maxY = MAP_INITIAL_VIEWBOX.y + MAP_INITIAL_VIEWBOX.h - newH;
    newX = clamp(newX, minX, Math.max(minX, maxX));
    newY = clamp(newY, minY, Math.max(minY, maxY));

    return { x: newX, y: newY, w: newW, h: newH };
  };

  const handlePointerDown = (e) => {
    activePointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (activePointersRef.current.size === 2) {
      // 2本目の指が触れた瞬間、単指パンを中断してピンチモードへ切り替える
      dragStateRef.current = null;
      didDragRef.current = false;
      setIsDragging(false);

      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const pts = [...activePointersRef.current.values()];
      const distance = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const centerXPixel = (pts[0].x + pts[1].x) / 2;
      const centerYPixel = (pts[0].y + pts[1].y) / 2;
      pinchStateRef.current = {
        initialDistance: distance,
        startViewBox: viewBox,
        centerXRatio: (centerXPixel - rect.left) / rect.width,
        centerYRatio: (centerYPixel - rect.top) / rect.height,
      };
      return;
    }

    if (activePointersRef.current.size > 2) return; // 3本指以降は無視

    // ここではsetPointerCaptureを呼ばない。無条件に呼ぶと、単なるクリックの
    // 場合でもクリックイベントの発生先がsvg自体にすり替わってしまい、
    // ピン・国のonClickが発火しなくなる不具合が実際に発生したため、
    // 実際にドラッグと判定された時点(handlePointerMove内)でのみ捕捉する。
    dragStateRef.current = { startX: e.clientX, startY: e.clientY, startViewBox: viewBox };
    didDragRef.current = false;
    setIsDragging(true);
  };

  const handlePointerMove = (e) => {
    if (activePointersRef.current.has(e.pointerId)) {
      activePointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    // --- ピンチズーム中(2本指) ---
    if (activePointersRef.current.size === 2 && pinchStateRef.current) {
      const pts = [...activePointersRef.current.values()];
      const distance = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const { initialDistance, startViewBox, centerXRatio, centerYRatio } = pinchStateRef.current;
      if (initialDistance < 1) return;

      // 指の間隔が広がる=拡大したい=viewBoxは縮小(factor<1)。ホイールの
      // deltaYと符号の意味が逆になる点に注意(ホイールは下スクロールで縮小)。
      const factor = initialDistance / distance;
      setViewBox(zoomViewBoxAround(startViewBox, factor, centerXRatio, centerYRatio));
      return;
    }

    // --- 単指パン中 ---
    if (activePointersRef.current.size !== 1) return;
    if (!dragStateRef.current) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const { startX, startY, startViewBox } = dragStateRef.current;
    const dxPixels = e.clientX - startX;
    const dyPixels = e.clientY - startY;

    if (Math.abs(dxPixels) + Math.abs(dyPixels) > 3) {
      if (!didDragRef.current) {
        // ここで初めてドラッグとして確定させ、このタイミングでのみポインタを捕捉する
        try {
          svg.setPointerCapture(e.pointerId);
        } catch (err) {
          // すでに別要因で無効化されている場合等は無視
        }
      }
      didDragRef.current = true;
    }

    if (!didDragRef.current) return; // 閾値未満の微小な動きではパンしない(誤操作防止)

    const scaleX = startViewBox.w / rect.width;
    const scaleY = startViewBox.h / rect.height;
    let newX = startViewBox.x - dxPixels * scaleX;
    let newY = startViewBox.y - dyPixels * scaleY;

    const minX = MAP_INITIAL_VIEWBOX.x;
    const maxX = MAP_INITIAL_VIEWBOX.x + MAP_INITIAL_VIEWBOX.w - startViewBox.w;
    const minY = MAP_INITIAL_VIEWBOX.y;
    const maxY = MAP_INITIAL_VIEWBOX.y + MAP_INITIAL_VIEWBOX.h - startViewBox.h;
    newX = clamp(newX, minX, maxX);
    newY = clamp(newY, minY, maxY);

    setViewBox((prev) => ({ ...prev, x: newX, y: newY }));
  };

  const handlePointerUp = (e) => {
    activePointersRef.current.delete(e.pointerId);

    if (activePointersRef.current.size < 2) {
      pinchStateRef.current = null;
    }

    if (activePointersRef.current.size === 0) {
      const svg = svgRef.current;
      if (svg && svg.hasPointerCapture?.(e.pointerId)) {
        svg.releasePointerCapture(e.pointerId);
      }
      dragStateRef.current = null;
      setIsDragging(false);
    }
  };

  // 実際にドラッグしていた場合のみ、直後のクリックをピン・国の選択として扱わない
  // (ドラッグ確定時にはポインタキャプチャの効果でクリックの発生先がsvgに
  // すり替わるため、この処理は主に保険的な役割)
  const handleClickCapture = (e) => {
    if (didDragRef.current) {
      e.stopPropagation();
      didDragRef.current = false;
    }
  };

  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A]" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">Coffee Belt Map</p>
        <span className="text-[10px] text-[#8B7361]">ピンチ/ホイールで拡大縮小、ドラッグで移動</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
        {Object.keys(MAP_REGION_PRESETS).map((region) => (
          <button
            key={region}
            onClick={() => setViewBox(MAP_REGION_PRESETS[region])}
            className="text-[11px] px-3 py-1 rounded-full border border-[var(--accent-label)] text-[var(--accent)] hover:bg-[#3B2211] transition-colors"
          >
            {region}
          </button>
        ))}
        {isZoomed && (
          <button
            onClick={resetZoom}
            className="text-[11px] px-3 py-1 rounded-full border border-[#4A3A2A] text-[#8B7361] hover:text-[var(--accent)] transition-colors"
          >
            全体表示
          </button>
        )}
      </div>

      <svg
        ref={svgRef}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onClickCapture={handleClickCapture}
        style={{
          width: "100%",
          height: "auto",
          display: "block",
          borderRadius: 12,
          touchAction: "none",
          cursor: isDragging ? "grabbing" : "grab",
        }}
      >
        <rect x="80" y="108" width="920" height="284" fill="#1C140D" />

        {/* 大陸の輪郭(背景) */}
        {Object.entries(CONTINENT_PATHS).map(([name, d]) => (
          <path key={name} d={d} fill="#2F241A" stroke="#3B2211" strokeWidth="0.6" />
        ))}

        {/* 赤道の帯(正距円筒図法でlat=0はy=250) */}
        <line x1="80" y1="250" x2="1000" y2="250" stroke="var(--accent-label)" strokeOpacity="0.4" strokeDasharray="6 6" />
        <text x="88" y="244" fontSize="11" fill="var(--accent-label)" opacity="0.8">赤道</text>

        {/* 日本(特別な強調はせず、大陸と同じ背景色で自然に溶け込ませる) */}
        <path d={JAPAN_PATH} fill="#2F241A" stroke="#3B2211" strokeWidth="0.6" />

        {/* 対象国(強調表示) */}
        {Object.entries(COUNTRY_PATHS).map(([name, d]) => (
          <path
            key={name}
            d={d}
            fill="var(--accent-label)"
            fillOpacity={isSelected(name) ? 1 : 0.85}
            stroke={isSelected(name) ? "var(--accent-soft)" : "var(--accent)"}
            strokeWidth={isSelected(name) ? 1.4 : 1}
            onClick={() => {
              const origin = origins.find((o) => o.country === name);
              if (origin) onSelect(origin);
            }}
            style={{ cursor: "pointer" }}
          />
        ))}

        {/* 産地ピン */}
        {/* 近接するピン同士でラベルが重なる国は、個別にラベル位置を調整する
            (ピン自体の位置=国境データ上の実座標は変更しない) */}
        {(() => {
          const LABEL_OVERRIDES = {
            "ジャマイカ": { dx: 34, dy: -18, anchor: "middle" },
            "ケニア": { dx: 12, dy: -14, anchor: "start" },
            "イエメン": { dx: 16, dy: -20, anchor: "start" },
            "タンザニア": { dx: 0, dy: 24, anchor: "middle" },
            "エチオピア": { dx: -10, dy: -14, anchor: "end" },
            "コスタリカ": { dx: -8, dy: 24, anchor: "end" },
            "コロンビア": { dx: 12, dy: -14, anchor: "start" },
            "エルサルバドル": { dx: -6, dy: 2, anchor: "end" },
          };
          return origins.map((origin) => {
            const pos = COUNTRY_MAP_POSITIONS[origin.country];
            if (!pos) return null;
            const selected_ = isSelected(origin.country);
            const override = LABEL_OVERRIDES[origin.country];
            const anchor = override?.anchor ?? "middle";
            const dy = override?.dy ?? -14;
            const labelX = pos.x + (override?.dx ?? 0);
            const labelY = pos.y + dy;
            const textWidth = origin.country.length * 10 + 10;
            const rectX =
              anchor === "start"
                ? labelX - 5
                : anchor === "end"
                ? labelX - textWidth + 5
                : labelX - textWidth / 2;
            // ラベルがピンの上にあるか下にあるかで、引き出し線の接続先を変える
            const lineEndY = dy >= 0 ? labelY - 8 : labelY + 4;

            return (
              <g
                key={origin.country}
                onClick={() => onSelect(origin)}
                style={{ cursor: "pointer" }}
              >
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={selected_ ? 6 : 4.5}
                  fill={selected_ ? "var(--accent)" : "var(--accent-soft)"}
                  stroke="#231810"
                  strokeWidth="1"
                />
                {override && (
                  <line
                    x1={pos.x}
                    y1={pos.y}
                    x2={labelX}
                    y2={lineEndY}
                    stroke={selected_ ? "var(--accent)" : "#8B7361"}
                    strokeWidth="0.8"
                  />
                )}
                <rect
                  x={rectX}
                  y={labelY - 12}
                  width={textWidth}
                  height="16"
                  rx="8"
                  fill={selected_ ? "var(--accent)" : "#3B2211"}
                  fillOpacity="0.95"
                />
                <text
                  x={labelX}
                  y={labelY}
                  fontSize="10.5"
                  textAnchor={anchor}
                  fill={selected_ ? "#231810" : "#B8A891"}
                  fontWeight={selected_ ? "600" : "400"}
                >
                  {origin.country}
                </text>
              </g>
            );
          });
        })()}
      </svg>
    </div>
  );
}
