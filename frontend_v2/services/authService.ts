import { User } from "../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const getHeaders = () => {
    const token = localStorage.getItem('token');
    return {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Token ${token}` } : {})
    };
};

export const signupUser = async (data: {
    fullName: string;
    email: string;
    password: string;
    phone: string;
    address: string;
    experienceDescription: string;
    educationLevel: string;
    resumeData: { name: string; type: string; url: string };
}) => {
    const response = await fetch(`${API_URL}/hr/auth/signup/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(data),
    });
    if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Signup failed");
    }
    const result = await response.json();
    return result.user as User;
};

export const loginUser = async (email: string, password: string): Promise<User> => {
    const response = await fetch(`${API_URL}/hr/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 403 && data.code === 'NOT_APPROVED') throw new Error("ACCOUNT_NOT_APPROVED");
        if (response.status === 403 && data.code === 'EMAIL_NOT_VERIFIED') throw new Error("EMAIL_NOT_VERIFIED");
        if (response.status === 403) throw new Error(String(data.detail || "FORBIDDEN"));
        throw new Error("INVALID_CREDENTIALS");
    }
    localStorage.setItem("token", data.token);
    if (data.user?.id) {
        localStorage.setItem("userId", String(data.user.id));
    }
    return data.user as User;
};

export const loginWithGoogle = async (): Promise<User> => {
    throw new Error("Google login temporarily disabled during API migration.");
};

export const resendVerificationEmail = async (email: string, password: string) => {
    const response = await fetch(`${API_URL}/hr/auth/resend-verification/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error("Failed to resend verification email");
};

export const changeUserPassword = async (oldPassword: string, newPassword: string) => {
    const response = await fetch(`${API_URL}/hr/auth/change-password/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ oldPassword, newPassword }),
    });
    if (!response.ok) throw new Error("Failed to change password");
};

export const logoutUser = async () => {
    try {
        await fetch(`${API_URL}/hr/auth/logout/`, {
            method: 'POST',
            headers: getHeaders(),
        });
    } catch {
        // ignore errors
    }
    localStorage.removeItem("token");
    localStorage.removeItem("userId");
};

export const fetchUserProfile = async (uid: string): Promise<User | null> => {
    try {
        const response = await fetch(`${API_URL}/hr/users/${uid}/`, {
            headers: getHeaders(),
        });
        if (!response.ok) return null;
        return (await response.json()) as User;
    } catch {
        return null;
    }
};