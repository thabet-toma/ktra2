import { createTheme } from '@mui/material/styles';

/**
 * Premium Enterprise Theme "Royal Navy"
 * Primary: Deep Navy Blue (Trust, Professionalism)
 * Secondary: Gold/Amber (Premium, Action)
 * Background: Soft Light Grey (Readability)
 */
const theme = createTheme({
    palette: {
        mode: 'light',
        primary: {
            main: '#0A1929', // Deep Navy
            light: '#1F3A56',
            dark: '#050D15',
            contrastText: '#ffffff',
        },
        secondary: {
            main: '#FFB300', // Amber Gold
            light: '#FFE54C',
            dark: '#C68400',
            contrastText: '#000000',
        },
        background: {
            default: '#F4F6F8', // Very light grey/blue tint
            paper: '#FFFFFF',
        },
        text: {
            primary: '#1A2027',
            secondary: '#4A5568',
        },
        success: {
            main: '#2e7d32',
        },
        warning: {
            main: '#ed6c02',
        },
        error: {
            main: '#d32f2f',
        },
        info: {
            main: '#0288d1',
        },
    },
    typography: {
        fontFamily: '"Cairo", "Roboto", "Helvetica", "Arial", sans-serif',
        h1: { fontWeight: 700 },
        h2: { fontWeight: 700 },
        h3: { fontWeight: 700 },
        h4: { fontWeight: 600, letterSpacing: '-0.5px' },
        h5: { fontWeight: 600 },
        h6: { fontWeight: 600 },
        button: { textTransform: 'none', fontWeight: 600 },
    },
    shape: {
        borderRadius: 12, // Modern rounded corners
    },
    components: {
        MuiButton: {
            styleOverrides: {
                root: {
                    borderRadius: 8,
                    boxShadow: 'none',
                    '&:hover': {
                        boxShadow: '0px 2px 4px -1px rgba(0,0,0,0.2), 0px 4px 5px 0px rgba(0,0,0,0.14), 0px 1px 10px 0px rgba(0,0,0,0.12)',
                    },
                },
                containedPrimary: {
                    background: 'linear-gradient(45deg, #0A1929 30%, #1F3A56 90%)',
                },
                containedSecondary: {
                    color: '#0A1929', // Contrast text for gold
                }
            },
        },
        MuiPaper: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                },
                elevation1: {
                    boxShadow: '0px 2px 8px rgba(0,0,0,0.05)', // Subtle shadow
                },
                elevation2: {
                    boxShadow: '0px 4px 16px rgba(0,0,0,0.08)', // Floating effect
                },
            },
        },
        MuiAppBar: {
            styleOverrides: {
                root: {
                    backgroundColor: '#ffffff',
                    color: '#0A1929',
                    boxShadow: '0px 1px 4px rgba(0,0,0,0.05)',
                },
            },
        },
        MuiChip: {
            styleOverrides: {
                root: {
                    fontWeight: 500,
                },
            },
        },
        MuiTableCell: {
            styleOverrides: {
                head: {
                    fontWeight: 'bold',
                    backgroundColor: '#F4F6F8',
                    color: '#1A2027',
                },
            },
        },
    },
});

export default theme;
