import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Bootstrap } from '../types'
import { api } from './api'
import { CATEGORIES, DAYS_TO_DIWALI, DEMO_TODAY, DIWALI_DATE, SAMPLE_MANAGER_PROMPTS, SAMPLE_SHOPPER_PROMPTS, STORES } from './constants'

const fallback: Bootstrap = {
  demo_today: DEMO_TODAY,
  diwali_date: DIWALI_DATE,
  days_to_diwali: DAYS_TO_DIWALI,
  stores: STORES,
  categories: CATEGORIES,
  sample_prompts: { shopper: SAMPLE_SHOPPER_PROMPTS, manager: SAMPLE_MANAGER_PROMPTS },
  reset_at: null,
}

const Ctx = createContext<Bootstrap>(fallback)

export function BootstrapProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<Bootstrap>(fallback)
  useEffect(() => {
    api
      .bootstrap()
      .then((b) =>
        setData({
          ...fallback,
          ...b,
          stores: b.stores?.length ? b.stores : fallback.stores,
          categories: b.categories?.length ? b.categories : fallback.categories,
          sample_prompts: {
            shopper: b.sample_prompts?.shopper?.length ? b.sample_prompts.shopper : fallback.sample_prompts.shopper,
            manager: b.sample_prompts?.manager?.length ? b.sample_prompts.manager : fallback.sample_prompts.manager,
          },
        }),
      )
      .catch(() => {
        /* keep the built-in reference data */
      })
  }, [])
  return <Ctx.Provider value={data}>{children}</Ctx.Provider>
}

export function useBootstrap() {
  return useContext(Ctx)
}
