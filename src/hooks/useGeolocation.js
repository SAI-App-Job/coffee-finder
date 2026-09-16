import { useCallback, useEffect, useState } from "react";

// status:
//   "idle"        取得を試みる前
//   "pending"     取得中(許可待ち含む)
//   "success"     取得成功
//   "denied"      利用者が拒否した
//   "unsupported" ブラウザがGeolocation APIに非対応
//   "error"       タイムアウト等、拒否以外の理由で取得できなかった
//
// 呼び出し側(App.jsx)は、"success"以外のあいだは新着順にフォールバックする方針
// (仕様書の「位置情報ソート」フォールバック要件)。
export function useGeolocation() {
  const [status, setStatus] = useState("idle");
  const [coords, setCoords] = useState(null);

  const request = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setStatus("unsupported");
      return;
    }
    setStatus("pending");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords({ lat: position.coords.latitude, lng: position.coords.longitude });
        setStatus("success");
      },
      (err) => {
        // PERMISSION_DENIED = 1。拒否された場合は再度自動で取得を試みない
        // (仕様書: 「許可を拒否された場合は距離順への切り替えは行わず、
        // 新着順のまま維持する」)。利用者が明示的に再試行ボタンを押した場合のみ
        // requestを呼び直す(その際はブラウザの許可設定次第で再度プロンプトが
        // 出ることもある)。
        setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 5 * 60 * 1000 }
    );
  }, []);

  // 端末内で完結させる方針のため、位置情報は毎回の起動時に取得を試みる
  // (サーバーへの送信・永続化は一切行わない)。
  useEffect(() => {
    request();
  }, [request]);

  return { status, coords, retry: request };
}
