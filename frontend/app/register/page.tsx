"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { HttpError } from "@/lib/xhr";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ username: "", email: "", password: "", display_name: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  function validate(): string | null {
    if (form.username.trim().length < 3) return "Username must be at least 3 characters.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) return "Enter a valid email address.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    if (!form.display_name.trim()) return "Display name is required.";
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) return setError(v);
    setError("");
    setLoading(true);
    try {
      await api.register(form);
      const tokens = await api.login({ username: form.username, password: form.password });
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/app");
    } catch (err) {
      if (err instanceof HttpError && err.status === 409) setError("Username or email already taken.");
      else setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center">
      <h2>Create account</h2>
      <form onSubmit={onSubmit} noValidate>
        <div className="field"><label>Username</label><input value={form.username} onChange={set("username")} autoFocus /></div>
        <div className="field"><label>Email</label><input value={form.email} onChange={set("email")} /></div>
        <div className="field"><label>Display name</label><input value={form.display_name} onChange={set("display_name")} /></div>
        <div className="field"><label>Password</label><input type="password" value={form.password} onChange={set("password")} /></div>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={loading} style={{ width: "100%", marginTop: 8 }}>
          {loading ? "Creating…" : "Register"}
        </button>
      </form>
      <p style={{ color: "var(--muted)", marginTop: 16 }}>
        Have an account? <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}
