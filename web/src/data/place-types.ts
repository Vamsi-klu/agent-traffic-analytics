// Where visitors' country, region and city come from, as /api/web, /api/health and /api/session/<id> say it
// (agentcake/api/places.py). Part of the /api contract of ./types.ts, which re-exports these types.

/** The credit a data source asks for on every page that shows its results (DB-IP's "IP Geolocation by DB-IP" link). */
export type Attribution = { text: string; url: string }
/** Where visitors' country, region and city come from: none (AgentCake on this computer sees no visitor addresses),
 *  missing (a server whose city database isn't downloaded yet), database (DB-IP's IP to City Lite on the server). */
export type PlaceSource = "none" | "missing" | "database"
/** The source of places, and DB-IP's credit while its database is in use. */
export type Places = { source: PlaceSource; attribution: Attribution | null }
