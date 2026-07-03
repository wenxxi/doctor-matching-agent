export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50">
      <section className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
        <p className="mb-4 text-sm font-semibold uppercase tracking-wide text-teal-700">
          MVP Foundation
        </p>
        <h1 className="text-4xl font-bold tracking-normal text-slate-950 sm:text-6xl">
          Doctor Matching Agent
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-700">
          A production-ready starting point for matching patients with doctors,
          ready for backend services, data pipelines, and future agent workflows.
        </p>
      </section>
    </main>
  );
}

