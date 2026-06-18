"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { HttpError } from "@/lib/xhr";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);

  // Raw-XHR-backed submit with client-side validation.
  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (username.trim().length < 3) return setError("Username must be at least 3 characters.");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    setLoading(true);
    try {
      const tokens = await api.login({ username, password }, setProgress);
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/app");
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) setError("Invalid credentials.");
      else if (err instanceof HttpError && err.status === 429) setError("Too many attempts — wait a moment.");
      else setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center">
      <h2>Sign in</h2>
      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <div className="error">{error}</div>}
        {loading && <div className="progress" style={{ width: `${Math.max(8, progress * 100)}%` }} />}
        <button type="submit" disabled={loading} style={{ width: "100%", marginTop: 8 }}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p style={{ color: "var(--muted)", marginTop: 16 }}>
        No account? <Link href="/register">Register</Link>
      </p>
      <p style={{ color: "var(--muted)", fontSize: 12 }}>
        Demo: <b>dispatch_admin</b> / <b>password123</b>
      </p>
    </div>
  );
}
