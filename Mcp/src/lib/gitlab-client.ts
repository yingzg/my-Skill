import axios, { AxiosInstance, AxiosRequestConfig } from "axios";

export class GitLabClient {
  private readonly axiosInstance: AxiosInstance;

  constructor(apiUrl: string, token: string) {
    this.axiosInstance = axios.create({
      baseURL: apiUrl,
      timeout: 15000,
      headers: {
        "PRIVATE-TOKEN": token,
      },
    });
  }

  async get<T = unknown>(path: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.axiosInstance.get<T>(path, config);
    return response.data;
  }

  async post<T = unknown>(path: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.axiosInstance.post<T>(path, data, config);
    return response.data;
  }

  async put<T = unknown>(path: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.axiosInstance.put<T>(path, data, config);
    return response.data;
  }

  async delete<T = unknown>(path: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.axiosInstance.delete<T>(path, config);
    return response.data;
  }

  projectPath(projectId: string | number): string {
    return `/projects/${encodeGitLabPath(projectId)}`;
  }
}

export function encodeGitLabPath(value: string | number): string {
  const raw = String(value);
  try {
    const decoded = decodeURIComponent(raw);
    return encodeURIComponent(decoded);
  } catch {
    return encodeURIComponent(raw);
  }
}

