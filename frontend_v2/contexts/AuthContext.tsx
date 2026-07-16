
import React, { createContext, useContext, useEffect, useState } from 'react';
import { User } from '../types';
import { fetchUserProfile as fetchUserProfileApi, logoutUser as logoutApi } from '../services/authService';
import { activityService } from '../services/firestoreService';
import { clientLogger } from '../services/logger';

interface AuthContextType {
    currentUser: User | null;
    loading: boolean;
    logout: () => Promise<void>;
    updateUser: (user: User) => void;
    /** بعد نجاح loginUser (يُحفظ التوكن) — يعيد تحميل الملف الشخصي من المرآة */
    refreshSession: () => Promise<void>;
    /** يضبط المستخدم بعد تسجيل الدخول مباشرة (تحديث فوري + نشاط) — لا يعتمد على إعادة تشغيل initAuth */
    completeLogin: (user: User) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Activity/points are secondary session data. A slow mapper request must never
 * hold the authenticated application shell behind the global loading screen.
 */
const bootstrapActivityStatus = async (userId: string): Promise<void> => {
    try {
        const status = await activityService.getActivityStatus(userId);
        if (!status) {
            await activityService.initializeActivityStatus(userId);
        }
    } catch (error) {
        clientLogger.warn('auth.activity_bootstrap_failed', {
            userId,
            error: error instanceof Error ? error.message : String(error),
        });
    }
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchUserProfile = async (userId: string): Promise<User | null> => {
        try {
            return await fetchUserProfileApi(userId);
        } catch (error) {
            // console suppressed
            return null;
        }
    };

    const applyUserSession = async (userId: string) => {
        const userProfile = await fetchUserProfile(userId);
        if (userProfile && userProfile.isApproved) {
            setCurrentUser(userProfile);
            void bootstrapActivityStatus(userProfile.id);
        } else {
            setCurrentUser(null);
        }
    };

    const refreshSession = async () => {
        const token = localStorage.getItem('token');
        const userId = localStorage.getItem('userId');
        if (token && userId) {
            await applyUserSession(userId);
        } else {
            setCurrentUser(null);
        }
    };

    const completeLogin = async (user: User) => {
        setCurrentUser(user);
        void bootstrapActivityStatus(user.id);
    };

    useEffect(() => {
        const initAuth = async () => {
            setLoading(true);
            const token = localStorage.getItem('token');
            const userId = localStorage.getItem('userId');

            if (token && userId) {
                try {
                    await applyUserSession(userId);
                } catch (error) {
                    // console suppressed
                    setCurrentUser(null);
                }
            } else {
                setCurrentUser(null);
            }
            setLoading(false);
        };

        initAuth();
    }, []);

    const logout = async () => {
        await logoutApi();
        setCurrentUser(null);
    };

    const updateUser = (user: User) => {
        setCurrentUser(user);
    }

    return (
        <AuthContext.Provider value={{ currentUser, loading, logout, updateUser, refreshSession, completeLogin }}>
            {children}
        </AuthContext.Provider>
    );
};
