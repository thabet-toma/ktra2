
import React, { createContext, useContext, useEffect, useState } from 'react';
import { User } from '../types';
import { fetchUserProfile as fetchUserProfileApi, logoutUser as logoutApi } from '../services/authService';
import { activityService } from '../services/firestoreService';

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
            console.error("Error fetching user profile:", error);
            return null;
        }
    };

    const applyUserSession = async (userId: string) => {
        const userProfile = await fetchUserProfile(userId);
        if (userProfile && userProfile.isApproved) {
            setCurrentUser(userProfile);
            try {
                const status = await activityService.getActivityStatus(userProfile.id);
                if (!status) {
                    await activityService.initializeActivityStatus(userProfile.id);
                }
            } catch (err) {
                console.error("Error initializing activity:", err);
            }
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
        try {
            const status = await activityService.getActivityStatus(user.id);
            if (!status) {
                await activityService.initializeActivityStatus(user.id);
            }
        } catch (err) {
            console.error("Error initializing activity:", err);
        }
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
                    console.error(error);
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
