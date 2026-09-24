"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginContent() {
  const searchParams = useSearchParams();
  const failed = searchParams.get("error") === "oauth_failed";

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="brand-mark" aria-hidden="true">✓</div>
        <p className="eyebrow">TASKFLOW</p>
        <h1>Keep work moving.</h1>
        <p className="login-copy">
          Create, assign, and complete tasks with your team. Sign in with your Google account to begin.
        </p>
        {failed && <p className="alert error">Google sign-in failed. Please try again.</p>}
        <a className="google-button" href="/backend-api/auth/google">
          <span className="google-g" aria-hidden="true">G</span>
          Continue with Google
        </a>
        <p className="privacy-note">We only use your basic Google profile to identify your account.</p>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="login-shell"><p>Loading…</p></main>}>
      <LoginContent />
    </Suspense>
  );
}
