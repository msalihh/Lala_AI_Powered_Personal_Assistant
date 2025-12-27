"use client";

import { useEffect } from "react";
import { Box, Button, Heading, Text, VStack } from "@chakra-ui/react";
import { useRouter } from "next/navigation";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error("Error:", error);
  }, [error]);

  return (
    <Box
      minH="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      bg="gray.50"
      p={8}
    >
      <VStack spacing={4} maxW="500px" textAlign="center">
        <Heading size="lg" color="red.500">
          Bir hata oluştu
        </Heading>
        <Text color="gray.600">
          {error.message || "Beklenmeyen bir hata meydana geldi"}
        </Text>
        <VStack spacing={2} mt={4}>
          <Button colorScheme="blue" onClick={reset}>
            Tekrar Dene
          </Button>
          <Button variant="outline" onClick={() => router.push("/")}>
            Ana Sayfaya Dön
          </Button>
        </VStack>
      </VStack>
    </Box>
  );
}

