import { useCallback, useEffect, useState } from "react";
import { api, mediaUrl } from "../api";
import { EmptyState, ErrorBanner, PageLoader } from "../components/Feedback";
import Icon from "../components/Icons";
import Modal from "../components/Modal";
import { formatDate } from "../utils";

export default function Watchlist() {
  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState(null);
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api("/api/watchlist");
      setPeople(data);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const openDialog = (type, person = null) => {
    setDialog({ type, person });
    setFormError("");
    setFiles([]);
    setName(type === "rename" ? person?.name || "" : "");
  };

  const closeDialog = () => {
    if (busy) return;
    setDialog(null);
    setFormError("");
    setFiles([]);
  };

  const submitAdd = async (event) => {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("Enter a name");
      return;
    }
    if (files.length !== 1) {
      setFormError("Choose 1 photo");
      return;
    }
    const form = new FormData();
    form.append("name", name.trim());
    files.forEach((file) => form.append("files", file));
    setBusy(true);
    setFormError("");
    try {
      await api("/api/watchlist", { method: "POST", body: form });
      setNotice(`${name.trim()} added to the watchlist`);
      setDialog(null);
      await load();
    } catch (exc) {
      setFormError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const submitRename = async (event) => {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("Enter a name");
      return;
    }
    setBusy(true);
    setFormError("");
    try {
      await api(`/api/watchlist/${dialog.person.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: name.trim() }),
      });
      setNotice("Watchlist entry renamed");
      setDialog(null);
      await load();
    } catch (exc) {
      setFormError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const submitPhotos = async (event) => {
    event.preventDefault();
    if (files.length !== 1) {
      setFormError("Choose 1 photo");
      return;
    }
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    setBusy(true);
    setFormError("");
    try {
      await api(`/api/watchlist/${dialog.person.id}/photos`, {
        method: "POST",
        body: form,
      });
      setNotice("Photos added and embedding recalculated");
      setDialog(null);
      await load();
    } catch (exc) {
      setFormError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    setBusy(true);
    setFormError("");
    try {
      await api(`/api/watchlist/${dialog.person.id}`, { method: "DELETE" });
      setNotice(`${dialog.person.name} removed from the watchlist`);
      setDialog(null);
      await load();
    } catch (exc) {
      setFormError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  const galleryPhotos = dialog?.type === "gallery" ? dialog.person.photos : [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Known people</p>
          <h1>Watchlist</h1>
          <p className="muted">
            Enroll with 1 clear photo per person. The image is resampled and stored locally.
          </p>
        </div>
        <button type="button" className="primary-button" onClick={() => openDialog("add")}>
          <Icon name="plus" size={16} />
          Add person
        </button>
      </div>

      {notice ? <div className="notice-banner">{notice}</div> : null}
      <ErrorBanner message={error} onRetry={load} />

      {loading ? (
        <PageLoader label="Loading watchlist" />
      ) : people.length === 0 ? (
        <EmptyState
          title="Your watchlist is empty"
          message="Add someone with 1 photo to start receiving confirmed alerts."
          action={
            <button type="button" className="primary-button" onClick={() => openDialog("add")}>
              Add first person
            </button>
          }
        />
      ) : (
        <div className="person-grid">
          {people.map((person) => (
            <article className="person-card" key={person.id}>
              <button
                type="button"
                className="person-photo"
                onClick={() => openDialog("gallery", person)}
                aria-label={`View photos of ${person.name}`}
              >
                {person.thumbnail_url ? (
                  <img src={mediaUrl(person.thumbnail_url)} alt={person.name} />
                ) : (
                  <span className="photo-placeholder" />
                )}
                <span className="photo-count">
                  {person.photo_count} {person.photo_count === 1 ? "photo" : "photos"}
                </span>
              </button>
              <div className="person-body">
                <div>
                  <h3>{person.name}</h3>
                  <p className="muted">Added {formatDate(person.created_at)}</p>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className="ghost-button small"
                    onClick={() => openDialog("photos", person)}
                  >
                    <Icon name="upload" size={14} />
                    Add photos
                  </button>
                  <button
                    type="button"
                    className="ghost-button small"
                    onClick={() => openDialog("rename", person)}
                  >
                    <Icon name="edit" size={14} />
                    Rename
                  </button>
                  <button
                    type="button"
                    className="ghost-button small danger"
                    onClick={() => openDialog("delete", person)}
                  >
                    <Icon name="trash" size={14} />
                    Delete
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {dialog?.type === "add" ? (
        <Modal title="Add person" onClose={closeDialog}>
          <form onSubmit={submitAdd} className="stack">
            <label className="field">
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Alex Morgan"
                maxLength={80}
                autoFocus
              />
            </label>
            <label className="field">
              <span>Photo</span>
              <input
                type="file"
                accept="image/*"
                onChange={(event) => setFiles(Array.from(event.target.files || []))}
              />
              <span className="field-hint">
                Use a clear, front-facing photo with one face. It is resampled automatically.
                {files.length} selected.
              </span>
            </label>
            {formError ? <p className="form-error">{formError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={closeDialog}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? "Enrolling..." : "Add to watchlist"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {dialog?.type === "rename" ? (
        <Modal title={`Rename ${dialog.person.name}`} onClose={closeDialog}>
          <form onSubmit={submitRename} className="stack">
            <label className="field">
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={80}
                autoFocus
              />
            </label>
            {formError ? <p className="form-error">{formError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={closeDialog}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? "Saving..." : "Save name"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {dialog?.type === "photos" ? (
        <Modal title={`Add photos for ${dialog.person.name}`} onClose={closeDialog}>
          <form onSubmit={submitPhotos} className="stack">
            <label className="field">
              <span>Photo</span>
              <input
                type="file"
                accept="image/*"
                onChange={(event) => setFiles(Array.from(event.target.files || []))}
              />
              <span className="field-hint">
                The image is resampled automatically after upload. {files.length} selected.
              </span>
            </label>
            {formError ? <p className="form-error">{formError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={closeDialog}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? "Uploading..." : "Add photos"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {dialog?.type === "delete" ? (
        <Modal
          title="Remove from watchlist"
          onClose={closeDialog}
          footer={
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={closeDialog}>
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={confirmDelete}
                disabled={busy}
              >
                {busy ? "Removing..." : "Remove person"}
              </button>
            </div>
          }
        >
          <p>
            Remove <strong>{dialog.person.name}</strong> and their enrolled photos? Past alerts
            will remain in the history.
          </p>
          {formError ? <p className="form-error">{formError}</p> : null}
        </Modal>
      ) : null}

      {dialog?.type === "gallery" ? (
        <Modal title={dialog.person.name} onClose={closeDialog} wide>
          <div className="photo-gallery">
            {galleryPhotos.map((photo) => (
              <a
                key={photo.id}
                href={mediaUrl(photo.url)}
                target="_blank"
                rel="noreferrer"
                className="gallery-item"
              >
                <img src={mediaUrl(photo.url)} alt={`${dialog.person.name} enrollment`} />
              </a>
            ))}
          </div>
          <p className="muted">Click a photo to open the full-size image.</p>
        </Modal>
      ) : null}
    </div>
  );
}
