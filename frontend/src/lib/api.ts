import axios, { type AxiosInstance } from "axios";

export interface APIResponse<T> {
  success: boolean;
  data: T | null;
  message?: string;
  request_id?: string;
}

export interface ErrorResponse {
  success: false;
  error: { code: string; message: string; field?: string };
  request_id?: string;
}

const api: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export { api as apiClient };
export default api;
