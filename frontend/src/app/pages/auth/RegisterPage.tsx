import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, TriangleAlert, UserPlus } from "lucide-react";

import { toApiError } from "@/api/client";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui";
import { useAuthStore } from "@/stores/useAuthStore";

export function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;
  const valid = name.trim() && email.trim() && password.length >= 8 && !mismatch;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending || !valid) return;
    setPending(true);
    setError(null);
    try {
      await register(email.trim(), password, name.trim());
      navigate("/", { replace: true });
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <Card accent className="card-hero">
      <CardHeader>
        <CardTitle className="flex flex-col items-center gap-1.5 text-center">
          <span className="text-2xl font-bold tracking-tight">AI Learning Companion</span>
          <span className="text-sm font-medium text-muted-foreground">
            Create your account — start learning in seconds.
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="register-name" className="text-sm font-medium">
              Display name
            </label>
            <Input
              id="register-name"
              type="text"
              autoComplete="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ada Lovelace"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="register-email" className="text-sm font-medium">
              Email
            </label>
            <Input
              id="register-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="register-password" className="text-sm font-medium">
              Password
            </label>
            <Input
              id="register-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="register-password-hint"
            />
            <p id="register-password-hint" className="text-xs text-muted-foreground">
              At least 8 characters.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="register-confirm" className="text-sm font-medium">
              Confirm password
            </label>
            <Input
              id="register-confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              aria-invalid={mismatch}
            />
            {mismatch ? (
              <p role="alert" className="text-xs text-destructive">
                Passwords do not match.
              </p>
            ) : null}
          </div>
          {error ? (
            <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
              <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={pending || !valid}>
            {pending ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Creating account…
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                <UserPlus className="h-4 w-4" aria-hidden="true" />
                Create account
              </span>
            )}
          </Button>
          <p className="text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
