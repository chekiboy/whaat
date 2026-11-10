import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { CreatedIdentity } from "@/client";
import {
  browseMemoriesQueryKey,
  createIdentityMutation,
  listIdentitiesQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { useTranslation } from "@/i18n";
import { IDENTITY_ID } from "@/lib/identities";

/** Adding an identity: a name, then its token, shown once with a copy button (here, or by the caller that takes
    `onCreated`). The server keeps the token too, so whaat can later write it into the identity's agent config. */
export function CreateIdentity({ onCreated }: { onCreated?: (identity: CreatedIdentity) => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<CreatedIdentity | null>(null);
  const mutation = useMutation({
    ...createIdentityMutation(),
    onSuccess: async (identity) => {
      setCreated(identity);
      setName("");
      await queryClient.invalidateQueries({ queryKey: listIdentitiesQueryKey() });
      await queryClient.invalidateQueries({ queryKey: browseMemoriesQueryKey() });
      onCreated?.(identity);
    },
  });
  const valid = IDENTITY_ID.test(name);
  const failure = mutation.error as { detail?: unknown } | null;
  const exists = typeof failure?.detail === "string" && failure.detail.includes("already");
  const error = !mutation.isError
    ? null
    : exists
      ? t("identities.exists", { name: mutation.variables?.body.id ?? "" })
      : t("identities.failed");
  return (
    <div className="id-create">
      <form
        className="id-add"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) mutation.mutate({ body: { id: name } });
        }}
      >
        <input
          className="sh-search st-input id-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("identities.namePlaceholder")}
          maxLength={32}
          spellCheck={false}
          aria-label={t("identities.name")}
        />
        <button type="submit" className="dv-btn on" disabled={!valid || mutation.isPending}>
          + {t("identities.create")}
        </button>
        <small className={name && !valid ? "bad" : undefined}>{t("identities.nameRule")}</small>
      </form>
      {error && <p className="id-error">{error}</p>}
      {created && !onCreated && <TokenOnce issued={created} />}
    </div>
  );
}

/** A token shown once: created with its identity, or regenerated, with a copy button. */
export function TokenOnce({ issued, regenerated = false }: { issued: CreatedIdentity; regenerated?: boolean }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* the token stays visible to copy by hand */
    }
  };
  return (
    <div className="id-once">
      <b>■ {t(regenerated ? "identities.regenerated" : "identities.created", { name: issued.id })}</b>
      <p>{t(regenerated ? "identities.regeneratedNote" : "identities.tokenNote")}</p>
      <div className="id-token">
        <code>WHAAT_TOKEN={issued.token}</code>
        <button type="button" onClick={copy}>
          ⧉ {copied ? t("identities.copied") : t("identities.copy")}
        </button>
      </div>
      {(issued.warnings ?? []).map((warning) => (
        <p key={warning} className="id-error">
          {warning}
        </p>
      ))}
    </div>
  );
}
