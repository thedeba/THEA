import { useState } from "react";
import { useAuth } from "../auth";
import Icon from "../components/Icons";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
    } catch (exc) {
      setError(exc.message || "Could not sign in");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <section className="login-intro">
        <div className="login-brand">
          <span className="brand-mark large">
            <Icon name="shield" size={30} />
          </span>
          <div>
            <strong>THEA</strong>
            <span>Local CCTV intelligence</span>
          </div>
        </div>
        <h1>Know who is on camera, in real time.</h1>
        <p>
          Face recognition, watchlist alerts and movement trails run entirely on your own
          network. No cloud account required.
        </p>
        <ul className="login-points">
          <li>
            <Icon name="camera" size={18} />
            Multiple RTSP cameras sampled at 3-5 FPS
          </li>
          <li>
            <Icon name="watchlist" size={18} />
            Watchlist matching with consecutive-frame confirmation
          </li>
          <li>
            <Icon name="trail" size={18} />
            Cross-camera movement trails and alert history
          </li>
        </ul>
      </section>

      <section className="login-card">
        <div>
          <p className="eyebrow">Secure dashboard</p>
          <h2>Sign in</h2>
          <p className="muted">Use the admin credentials configured on the server.</p>
        </div>
        <form onSubmit={submit} className="stack">
          <label className="field">
            <span>Username</span>
            <input
              type="text"
              value={username}
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button type="submit" className="primary-button wide" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="login-note">
          This dashboard handles sensitive footage. Keep it on a trusted network and change the
          default password.
        </p>
      </section>
    </div>
  );
}
