'use client';

/**
 * 认证上下文
 *
 * 提供全局的用户状态管理
 */

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import * as authApi from './api';
import type { AuthContextType, User } from './types';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // 获取当前用户
  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const userData = await authApi.getCurrentUser();
      setUser(userData);
    } catch (error) {
      console.error('Failed to fetch user:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // 登录
  const login = useCallback((returnTo?: string) => {
    authApi.login(returnTo);
  }, []);

  // 登出
  const logout = useCallback(async () => {
    try {
      const logoutUrl = await authApi.logout();
      window.location.href = logoutUrl;
    } catch (error) {
      console.error('Logout failed:', error);
    }
  }, []);

  // 初始化时获取用户信息
  useEffect(() => {
    refetch();
  }, [refetch]);

  return (
    <AuthContext.Provider value={{ user, loading, refetch, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * 使用认证上下文的 Hook
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
