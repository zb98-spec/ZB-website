import { redirect } from "next/navigation";
import { auth, signIn } from "@/auth";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) {
    redirect("/");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6 py-10">
      <div className="rounded-2xl border border-slate-800 bg-surface p-8 shadow-xl">
        <h1 className="text-2xl font-bold tracking-tight">Welcome to ZB Hub</h1>
        <p className="mt-2 text-sm text-slate-400">
          Sign in or create an account to get to your projects.
        </p>

        <div className="mt-8 flex flex-col gap-3">
          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo: "/" });
            }}
          >
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-3 rounded-md border border-slate-700 bg-white px-4 py-3 font-medium text-slate-900 transition hover:bg-slate-100"
            >
              <GoogleIcon />
              Continue with Google
            </button>
          </form>

          <form
            action={async () => {
              "use server";
              await signIn("apple", { redirectTo: "/" });
            }}
          >
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-3 rounded-md border border-slate-700 bg-black px-4 py-3 font-medium text-white transition hover:bg-slate-900"
            >
              <AppleIcon />
              Continue with Apple
            </button>
          </form>
        </div>

        <p className="mt-8 text-center text-xs text-slate-500">
          By continuing you agree to the terms for this hub. No password
          needed &mdash; your account is created automatically on first sign-in.
        </p>
      </div>
    </main>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.82-.07-1.42-.22-2.05H12v3.72h6.6c-.13 1.09-.85 2.74-2.45 3.85l-.02.15 3.56 2.7.25.02c2.26-2.06 3.58-5.09 3.58-8.39"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.05 7.93-2.86l-3.78-2.87c-1.01.7-2.38 1.19-4.15 1.19-3.17 0-5.86-2.06-6.82-4.92l-.14.01-3.7 2.82-.05.13C3.25 21.3 7.28 24 12 24"
      />
      <path
        fill="#FBBC05"
        d="M5.18 14.54A7.4 7.4 0 0 1 4.77 12c0-.88.16-1.74.4-2.54l-.01-.17-3.75-2.87-.12.06A11.96 11.96 0 0 0 0 12c0 1.93.47 3.76 1.29 5.38l3.89-2.84"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c2.25 0 3.77.96 4.64 1.77l3.39-3.3C17.94 1.19 15.24 0 12 0 7.28 0 3.25 2.7 1.29 6.62l3.88 2.84C6.14 6.8 8.83 4.75 12 4.75"
      />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
      <path d="M16.365 1.43c0 1.14-.463 2.24-1.222 3.05-.83.9-2.15 1.6-3.31 1.51-.15-1.1.42-2.28 1.19-3.05.83-.85 2.29-1.51 3.34-1.51zM20.6 17.14c-.55 1.27-.82 1.84-1.53 2.96-1 1.56-2.4 3.51-4.14 3.53-1.54.02-1.94-1.01-4.03-1-2.09.01-2.52 1.02-4.06 1-1.74-.02-3.06-1.77-4.06-3.33-2.78-4.31-3.07-9.37-1.36-12.06 1.22-1.92 3.14-3.04 4.94-3.04 1.84 0 2.99 1.01 4.51 1.01 1.47 0 2.37-1.01 4.51-1.01 1.6 0 3.3.87 4.51 2.38-3.96 2.17-3.32 7.83.71 9.56z" />
    </svg>
  );
}
