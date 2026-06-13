import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_sso: boolean;
  tenant_id: string;
  created_at: string;
}

export interface AdminRole {
  id: string;
  name: string;
  is_system: boolean;
  description: string | null;
}

export interface UserRoleRecord {
  id: string;
  user_id: string;
  role_id: string;
  assigned_by: string | null;
}

export function useAdminUsers() {
  return useQuery<AdminUser[]>({
    queryKey: ["admin-users"],
    queryFn: () => apiClient.get("/admin/users").then((r) => r.data),
  });
}

export function useAdminRoles() {
  return useQuery<AdminRole[]>({
    queryKey: ["admin-roles"],
    queryFn: () => apiClient.get("/admin/roles").then((r) => r.data),
  });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation<
    AdminUser,
    Error,
    { email: string; full_name: string; role_id?: string }
  >({
    mutationFn: (body) => apiClient.post("/admin/users/invite", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function usePatchAdminUser() {
  const qc = useQueryClient();
  return useMutation<
    AdminUser,
    Error,
    { id: string; body: { full_name?: string; is_active?: boolean } }
  >({
    mutationFn: ({ id, body }) =>
      apiClient.patch(`/admin/users/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useAssignRole() {
  const qc = useQueryClient();
  return useMutation<UserRoleRecord, Error, { userId: string; roleId: string }>({
    mutationFn: ({ userId, roleId }) =>
      apiClient
        .post(`/admin/users/${userId}/roles`, { role_id: roleId })
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useRevokeRole() {
  const qc = useQueryClient();
  return useMutation<void, Error, { userId: string; roleId: string }>({
    mutationFn: ({ userId, roleId }) =>
      apiClient
        .delete(`/admin/users/${userId}/roles/${roleId}`)
        .then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}
