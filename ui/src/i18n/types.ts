import type { en } from "./en";

/** The shape every language has: the English keys, each a string. A missing or extra key is a compile error. */
type Shape<T> = { [K in keyof T]: T[K] extends string ? string : Shape<T[K]> };
export type Dictionary = Shape<typeof en>;
