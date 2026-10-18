import type { Category, Store } from '../types'

export const DEMO_TODAY = '2026-10-18'
export const DIWALI_DATE = '2026-11-08'
export const DAYS_TO_DIWALI = 21
export const DEFAULT_STORE = 'CHN-TNG'
export const DEFAULT_CATEGORY: Category = 'sarees'

export const STORES: Store[] = [
  { store_id: 'CHN-TNG', name: 'T. Nagar', city: 'Chennai', type: 'store', languages: ['ta', 'en'] },
  { store_id: 'CHN-ANN', name: 'Anna Nagar', city: 'Chennai', type: 'store', languages: ['ta', 'en'] },
  { store_id: 'BLR-JAY', name: 'Jayanagar', city: 'Bengaluru', type: 'store', languages: ['kn', 'en', 'hi'] },
  { store_id: 'BLR-IND', name: 'Indiranagar', city: 'Bengaluru', type: 'store', languages: ['kn', 'en', 'hi'] },
  { store_id: 'CBE-RSP', name: 'RS Puram', city: 'Coimbatore', type: 'store', languages: ['ta', 'en'] },
  { store_id: 'HYD-BNJ', name: 'Banjara Hills', city: 'Hyderabad', type: 'store', languages: ['te', 'hi', 'en'] },
  { store_id: 'ONLINE', name: 'Online store', city: '', type: 'online', languages: ['en', 'hi', 'ta'] },
]

export const CATEGORIES: { category: Category; label: string }[] = [
  { category: 'sarees', label: 'Sarees' },
  { category: 'kurta_sets', label: "Women's Kurta Sets" },
  { category: 'mens_ethnic', label: "Men's Ethnic" },
  { category: 'home_decor', label: 'Festive Home Decor' },
  { category: 'gifting', label: 'Festive Gifting' },
  { category: 'footwear', label: 'Ethnic Footwear' },
]

export const SAMPLE_SHOPPER_PROMPTS = [
  'Maroon Kanchipuram silk saree for Diwali, under ₹5,000',
  'Royal blue kurta for men, size L',
  'Brass diya set for the puja room',
  'Diwali ke liye juttis chahiye, size 7',
  'தீபாவளிக்கு பட்டுப் புடவை வேண்டும்',
]

export const SAMPLE_MANAGER_PROMPTS = [
  'Which sarees are customers asking for that we cannot sell?',
  'What should T. Nagar move in before Diwali?',
  'Why is the demand-sensed forecast higher than sales?',
]

export function storeName(id: string | null | undefined): string {
  if (!id) return ''
  return STORES.find((s) => s.store_id === id)?.name ?? id
}

export function storeCity(id: string | null | undefined): string {
  if (!id) return ''
  return STORES.find((s) => s.store_id === id)?.city ?? ''
}

export function categoryLabel(c: string | null | undefined): string {
  if (!c) return ''
  return CATEGORIES.find((x) => x.category === c)?.label ?? c
}
