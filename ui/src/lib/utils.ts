import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export type WithElementRef<T extends Record<string, any>, U extends Record<string, any> = { ref?: any }> = T & U;
export type WithoutChild<T extends Record<string, any>> = T;
export type WithoutChildrenOrChild<T extends Record<string, any>> = T;
export type WithoutChildren<T extends Record<string, any>> = T;
