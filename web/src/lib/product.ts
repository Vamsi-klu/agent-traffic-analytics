/** The product's name in the interface (top bar, browser title, home, Crumb's label): agentcake/data/product.json, read
 *  when the pages are built (vite.config.ts), so it changes in one place. Sentences from /api carry it already. */
export const PRODUCT_NAME: string = import.meta.env.VITE_PRODUCT_NAME
