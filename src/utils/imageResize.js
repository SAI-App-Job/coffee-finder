// 容量とのバランスで、長辺1024px・品質0.75(1枚あたり100〜250KB程度)。バックアップに含めたときのファイルが大きくなりすぎないようにする。
const MAX_EDGE = 1024;
const JPEG_QUALITY = 0.75;

// 画像ファイルを読み込んで、長辺が MAX_EDGE 以下の JPEG(Blob)に縮小する。
// スマホのカメラ写真は数MBあるので、端末内に保存する前に小さくする(数百KB程度になる)。
// EXIF の向きは、ブラウザが描画時に反映する(createImageBitmap / img 要素の既定動作)。
export async function resizeImageToBlob(file) {
  if (!file || !file.type.startsWith("image/")) throw new Error("not-an-image");

  const source = await loadImage(file);
  const scale = Math.min(1, MAX_EDGE / Math.max(source.width, source.height));
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  // PNG の透明部分が JPEG 化で黒くならないよう、白で塗ってから描く
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source.image, 0, 0, width, height);
  source.close?.();

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  if (!blob) throw new Error("encode-failed");
  return blob;
}

async function loadImage(file) {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      return { image: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
    } catch {
      // 非対応の形式などは、下の <img> 経由の読み込みを試す
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("decode-failed"));
      el.src = url;
    });
    return { image: img, width: img.naturalWidth, height: img.naturalHeight };
  } finally {
    URL.revokeObjectURL(url);
  }
}
