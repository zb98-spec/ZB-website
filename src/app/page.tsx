import Link from "next/link";
import { auth, signOut } from "@/auth";
import { prisma } from "@/lib/prisma";

export default async function HomePage() {
  const session = await auth();

  const projects = session?.user?.id
    ? await prisma.project.findMany({
        where: { userId: session.user.id },
        orderBy: { createdAt: "desc" },
      })
    : [];

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold tracking-tight">ZB Hub</span>
        {session?.user ? (
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button
              type="submit"
              className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              Sign out
            </button>
          </form>
        ) : (
          <Link
            href="/login"
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Sign in
          </Link>
        )}
      </header>

      {session?.user ? (
        <section className="mt-16">
          <h1 className="text-3xl font-bold tracking-tight">
            Welcome back{session.user.name ? `, ${session.user.name}` : ""}
          </h1>
          <p className="mt-2 text-slate-400">
            Here&apos;s everything you&apos;ve got running in one place.
          </p>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 p-6 text-slate-400">
                No projects yet. Add one directly in the database, or wire up
                a &quot;New project&quot; form here later.
              </div>
            ) : (
              projects.map((project) => (
                <a
                  key={project.id}
                  href={project.url ?? "#"}
                  className="rounded-xl border border-slate-800 bg-surface p-5 transition hover:border-accent"
                >
                  <h2 className="font-semibold">{project.name}</h2>
                  {project.description ? (
                    <p className="mt-1 text-sm text-slate-400">
                      {project.description}
                    </p>
                  ) : null}
                </a>
              ))
            )}
          </div>
        </section>
      ) : (
        <section className="mt-24 flex flex-1 flex-col items-center text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            One place for everything you build.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-slate-400">
            ZB Hub is the central launchpad for all of my projects &mdash; sign
            in once, jump into anything.
          </p>
          <Link
            href="/login"
            className="mt-8 rounded-md bg-accent px-6 py-3 font-medium text-white transition hover:bg-indigo-500"
          >
            Get started
          </Link>
        </section>
      )}
    </main>
  );
}
