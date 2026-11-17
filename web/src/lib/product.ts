/** The product's name in the interface (top bar, browser title, home, Crumb's label): agentcake/data/product.json, read
 *  when the pages are built (vite.config.ts), so it changes in one place. Sentences from /api carry it already. */
export const PRODUCT_NAME: string = import.meta.env.VITE_PRODUCT_NAME

/** The repository at this version's tag (agentcake/data/product.json "source" with the version, read when the pages are
 *  built): an installed AgentCake carries the package only, so the documents a page names (SERVER.md) are there. */
export const SOURCE: string = import.meta.env.VITE_SOURCE
