// Node で、拡張子なしの import(src/ は、Vite 向けに、拡張子を省いて書いてある)を、.js として解決する。
// scripts/reduce-product-text.js が、src/utils/flavor.js を、そのまま使うための補助。
export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (e) {
    if (e.code === "ERR_MODULE_NOT_FOUND" && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) {
      return nextResolve(`${specifier}.js`, context);
    }
    throw e;
  }
}
