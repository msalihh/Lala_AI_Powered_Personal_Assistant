import { Box, Button, Heading, Text, VStack } from "@chakra-ui/react";
import Link from "next/link";

export default function NotFound() {
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
        <Heading size="2xl" color="gray.700">
          404
        </Heading>
        <Heading size="lg" color="gray.600">
          Sayfa Bulunamadı
        </Heading>
        <Text color="gray.500">
          Aradığınız sayfa mevcut değil veya taşınmış olabilir.
        </Text>
        <Button as={Link} href="/" colorScheme="blue" mt={4}>
          Ana Sayfaya Dön
        </Button>
      </VStack>
    </Box>
  );
}

