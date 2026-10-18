import { ManagerView } from '../features/manager/ManagerView'
import { Footer } from '../components/AppHeader'

export default function ManagerPage() {
  return (
    <>
      <main id="main" className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 sm:py-8">
        <ManagerView variant="page" />
      </main>
      <Footer />
    </>
  )
}
