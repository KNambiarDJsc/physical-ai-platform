"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, orgPath } from "@/lib/api/client";
import { Notice } from "./AppShell";
import { Table, Td } from "./ui";
import { OrgSelect, useOrg } from "./Workspace";

type Member = { user_id: string; issuer: string; subject: string; email: string | null; role: string };
const ROLES = ["viewer", "engineer", "admin"] as const;
const ROLE_HELP: Record<string, string> = {
  viewer: "reads everything; can ask for runs",
  engineer: "creates workflows and experiments; approves runs",
  admin: "also manages members and credentials",
};

/** Who is in the workspace and with which role. Admins add people by their sign-in identity and change roles. */
export function MembersPanel() {
  const { org, role, orgs, select } = useOrg();
  const qc = useQueryClient();
  const isAdmin = role === "admin";
  const members = useQuery({ queryKey: ["members", org], queryFn: () => api<Member[]>(`${orgPath(org!)}/members`), enabled: !!org });
  const me = useQuery({ queryKey: ["me-members", org], queryFn: () => api<{ subject?: string }>("/api/v1/me"), enabled: !!org });
  const [subject, setSubject] = useState("");
  const [newRole, setNewRole] = useState<(typeof ROLES)[number]>("viewer");
  const [issuerEdit, setIssuerEdit] = useState<string | null>(null);
  const ownIssuer = members.data?.find((m) => m.subject === me.data?.subject)?.issuer ?? members.data?.[0]?.issuer ?? "";
  const issuer = issuerEdit ?? ownIssuer;
  const refresh = () => void qc.invalidateQueries({ queryKey: ["members", org] });
  const put = useMutation({
    mutationFn: (b: { issuer: string; subject: string; role: string }) => api<Member>(`${orgPath(org!)}/members`, { method: "PUT", body: JSON.stringify(b) }),
    onSuccess: () => {
      setSubject("");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`${orgPath(org!)}/members/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  if (!org) return <p className="text-[13px] text-muted">You are not in a workspace yet.</p>;
  return (
    <div className="space-y-3 text-[13px]">
      <OrgSelect orgs={orgs} org={org} select={select} />
      {members.error && <Notice tone="bad">{members.error.message}</Notice>}
      {members.data && (
        <Table head={["Member", "Role", ""]} caption={`Members of ${org}`}>
          {members.data.map((m) => {
            const self = m.subject === me.data?.subject;
            return (
              <tr key={m.user_id}>
                <Td className="whitespace-normal">
                  {m.email ?? m.subject}
                  {self && <span className="ml-2 text-faint">(you)</span>}
                  {m.email && <span className="num block text-[12px] text-faint">{m.subject}</span>}
                </Td>
                <Td>
                  {isAdmin && !self ? (
                    <label>
                      <span className="sr-only">Role of {m.email ?? m.subject}</span>
                      <select className="field py-0.5" value={m.role} onChange={(e) => put.mutate({ issuer: m.issuer, subject: m.subject, role: e.target.value })}>
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    m.role
                  )}
                </Td>
                <Td>
                  {isAdmin && !self && (
                    <button className="text-accent hover:underline" disabled={remove.isPending} onClick={() => remove.mutate(m.user_id)}>
                      Remove {m.email ?? m.subject}
                    </button>
                  )}
                </Td>
              </tr>
            );
          })}
        </Table>
      )}
      {isAdmin ? (
        <form
          className="space-y-2 border-t border-line pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (subject.trim() && issuer.trim()) put.mutate({ issuer: issuer.trim(), subject: subject.trim(), role: newRole });
          }}
        >
          <p className="text-muted">Add someone by the identity they sign in with. They see the workspace the next time they sign in.</p>
          <div className="flex flex-wrap items-end gap-3">
            <label>
              <span className="mb-1 block text-muted">Their sign-in subject</span>
              <input className="field w-56" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="user id at the identity provider" />
            </label>
            <label>
              <span className="mb-1 block text-muted">Role for the new member</span>
              <select className="field" value={newRole} onChange={(e) => setNewRole(e.target.value as (typeof ROLES)[number])}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}: {ROLE_HELP[r]}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn btn-primary" type="submit" disabled={put.isPending || !subject.trim() || !issuer.trim()}>
              Add member
            </button>
          </div>
          <details className="text-[12px] text-muted">
            <summary className="cursor-pointer select-none">Identity provider</summary>
            <label className="mt-1 block">
              <span className="mb-1 block">Issuer (the same as yours unless they sign in elsewhere)</span>
              <input className="field num w-96 max-w-full" value={issuer} onChange={(e) => setIssuerEdit(e.target.value)} />
            </label>
          </details>
          {put.error && <Notice tone="bad">{put.error.message}</Notice>}
          {remove.error && <Notice tone="bad">{remove.error.message}</Notice>}
        </form>
      ) : (
        <p className="text-muted">An admin of this workspace adds members and changes roles.</p>
      )}
    </div>
  );
}
