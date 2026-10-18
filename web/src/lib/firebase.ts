// The Firebase web config is loaded at runtime from Firebase Hosting's reserved URL, so no keys live in the repo.
// Firestore rules make the demo collections read-only for browsers.
import { initializeApp, getApps } from 'firebase/app'
import { getFirestore, type Firestore } from 'firebase/firestore'

let dbPromise: Promise<Firestore> | null = null

export function getDb(): Promise<Firestore> {
  if (!dbPromise) {
    dbPromise = fetch('/__/firebase/init.json')
      .then((res) => {
        if (!res.ok) throw new Error(`Firebase config unavailable (${res.status})`)
        return res.json()
      })
      .then((config) => getFirestore(getApps()[0] ?? initializeApp(config)))
    dbPromise.catch(() => {
      dbPromise = null
    })
  }
  return dbPromise
}

export * from 'firebase/firestore'
