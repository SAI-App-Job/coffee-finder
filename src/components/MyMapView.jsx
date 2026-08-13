import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { MapPin, Heart } from "lucide-react";
import { SectionHeading } from "./common";
import { shopToPins, spreadOverlappingPins } from "../utils/mapPins";

// Viteのバンドル環境ではLeafletのデフォルトマーカー画像への相対パス解決が
// 壊れるため、バンドラーが解決したURLを明示的に差し替える(Leaflet+Vite定番の対処)。
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const JAPAN_CENTER = [36.5, 138];
const JAPAN_DEFAULT_ZOOM = 5;

function popupHtml(pin) {
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(pin.mapQuery)}`;
  return `
    <div style="font-family:Inter,sans-serif;min-width:160px">
      ${pin.label ? `<p style="font-size:11px;color:var(--accent-label);text-transform:uppercase;letter-spacing:0.05em;margin:0 0 2px">${pin.label}</p>` : ""}
      <p style="font-size:14px;font-weight:600;color:#231810;margin:0 0 4px">${pin.shopName}</p>
      ${pin.address ? `<p style="font-size:12px;color:#4A3A2A;margin:0 0 8px">${pin.address}</p>` : ""}
      ${pin.approximate ? `<p style="font-size:10px;color:#8B7361;margin:0 0 8px">※近隣に他拠点があるため位置は目安です</p>` : ""}
      <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" style="font-size:12px;color:var(--accent-label);text-decoration:underline">Googleマップで開く</a>
    </div>
  `;
}

// お気に入り商品を扱う店舗(App.jsxで導出済み)を、Leaflet + OpenStreetMapの
// タイルで地図表示する。Google Maps APIキーは使わない方針のためLeafletを自前実装。
export function MyMapView({ favoriteShops }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);

  const pins = spreadOverlappingPins(favoriteShops.flatMap(shopToPins));

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: JAPAN_CENTER,
      zoom: JAPAN_DEFAULT_ZOOM,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = pins.map((pin) => L.marker([pin.lat, pin.lng]).bindPopup(popupHtml(pin)).addTo(map));

    // タブ切替直後は親要素のレイアウトが確定する前にLeafletがコンテナサイズを
    // キャッシュしてしまい、fitBoundsのズーム計算が大きくずれることがある。
    // 表示のたびにコンテナサイズを再計測させてから範囲調整する。
    map.invalidateSize();

    if (pins.length > 0) {
      const bounds = L.latLngBounds(pins.map((p) => [p.lat, p.lng]));
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 });
    } else {
      map.setView(JAPAN_CENTER, JAPAN_DEFAULT_ZOOM);
    }
    // pinsは毎レンダーで新しい配列を作るため、内容を表す文字列で依存比較する
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(pins.map((p) => p.id))]);

  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <SectionHeading en="My Map" ja="マイマップ" />
      <p className="text-[13px] text-[#8B7361]">
        お気に入り商品を扱う店舗を自動的に地図表示します({pins.length}拠点)
      </p>

      {favoriteShops.length === 0 && (
        <div className="text-center py-10 text-[#8B7361]">
          <Heart size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">お気に入り商品を追加すると、取扱店舗がここに表示されます</p>
        </div>
      )}

      <div className="rounded-2xl overflow-hidden border border-[#4A3A2A]">
        <div ref={containerRef} className="w-full h-[60vh] min-h-[360px]" />
      </div>

      {favoriteShops.length > 0 && (
        <div className="flex flex-col gap-2 mt-1">
          {favoriteShops.map((shop) => (
            <div key={shop.name} className="flex items-center gap-2 text-[12px] text-[#8B7361]">
              <MapPin size={12} className="text-[var(--accent)] shrink-0" strokeWidth={1.75} />
              <span className="text-[#F2E9DD]">{shop.name}</span>
              {shop.locations && shop.locations.length > 1 && <span>・{shop.locations.length}拠点</span>}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
